//! REST endpoints driven by `.proto` `google.api.http` annotations and OpenAPI 3.1.

use std::convert::Infallible;

use axum::body::{Body, Bytes};
use axum::extract::rejection::JsonRejection;
use axum::http::header::{CACHE_CONTROL, CONTENT_TYPE};
use axum::http::{HeaderName, StatusCode};
use axum::response::{Html, IntoResponse, Response};
use axum::routing::{MethodRouter, delete, get, patch, post, put};
use axum::{Json, Router};
use serde_json::json;
use tokio::sync::mpsc;
use tokio_stream::wrappers::ReceiverStream;

use crate::generated_contract::{
    OPENAPI_JSON, REST_SAY_METHOD, REST_SAY_PATH, REST_STREAM_SAY_METHOD, REST_STREAM_SAY_PATH,
};
use crate::logic::{complete_reply, stream_reply};
use crate::proto::chat::v1::{SayRequest, SayResponse};
use crate::serialization::to_ndjson_line;

const SWAGGER_HTML: &str = r#"<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>chat - Swagger UI</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.ui = SwaggerUIBundle({
      url: '/openapi.json',
      dom_id: '#swagger-ui',
    });
  </script>
</body>
</html>
"#;

fn method_router<H, T>(method: &str, handler: H) -> MethodRouter
where
    H: axum::handler::Handler<T, ()>,
    T: 'static,
{
    match method {
        "GET" => get(handler),
        "PUT" => put(handler),
        "DELETE" => delete(handler),
        "PATCH" => patch(handler),
        _ => post(handler),
    }
}

pub fn router() -> Router {
    Router::new()
        .route(REST_SAY_PATH, method_router(REST_SAY_METHOD, chat_service_say))
        .route(
            REST_STREAM_SAY_PATH,
            method_router(REST_STREAM_SAY_METHOD, chat_service_stream_say),
        )
        .route("/api/health", get(health))
        .route("/openapi.json", get(openapi_json))
        .route("/docs", get(docs))
}

fn validate_payload(payload: Result<Json<SayRequest>, JsonRejection>) -> Result<SayRequest, Response> {
    let Json(body) = match payload {
        Ok(json) => json,
        Err(rejection) => {
            return Err((
                StatusCode::UNPROCESSABLE_ENTITY,
                Json(json!({ "detail": rejection.body_text() })),
            )
                .into_response());
        }
    };

    if body.text.trim().is_empty() {
        return Err((
            StatusCode::UNPROCESSABLE_ENTITY,
            Json(json!({ "detail": "text must be nonempty" })),
        )
            .into_response());
    }

    Ok(body)
}

async fn chat_service_say(payload: Result<Json<SayRequest>, JsonRejection>) -> Response {
    let body = match validate_payload(payload) {
        Ok(body) => body,
        Err(response) => return response,
    };

    match complete_reply(&body.text).await {
        Ok(reply) => (StatusCode::OK, Json(SayResponse { reply })).into_response(),
        Err(err) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({ "detail": err })),
        )
            .into_response(),
    }
}

async fn chat_service_stream_say(payload: Result<Json<SayRequest>, JsonRejection>) -> Response {
    let body = match validate_payload(payload) {
        Ok(body) => body,
        Err(response) => return response,
    };

    let (domain_tx, mut domain_rx) = mpsc::channel(16);
    let (out_tx, out_rx) = mpsc::channel::<Result<Bytes, Infallible>>(16);
    let text = body.text;

    tokio::spawn(async move {
        stream_reply(&text, domain_tx).await;
    });

    tokio::spawn(async move {
        while let Some(event) = domain_rx.recv().await {
            let line = Bytes::from(to_ndjson_line(&event));
            if out_tx.send(Ok(line)).await.is_err() {
                break;
            }
        }
    });

    (
        StatusCode::OK,
        [
            (CONTENT_TYPE, "application/x-ndjson"),
            (CACHE_CONTROL, "no-store"),
            (HeaderName::from_static("x-accel-buffering"), "no"),
        ],
        Body::from_stream(ReceiverStream::new(out_rx)),
    )
        .into_response()
}

async fn health() -> impl IntoResponse {
    Json(json!({ "status": "ok" }))
}

async fn openapi_json() -> impl IntoResponse {
    (
        StatusCode::OK,
        [(CONTENT_TYPE, "application/json")],
        OPENAPI_JSON,
    )
}

async fn docs() -> impl IntoResponse {
    Html(SWAGGER_HTML)
}
