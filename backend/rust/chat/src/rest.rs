//! REST endpoints driven by the `.proto` `google.api.http` annotation and OpenAPI 3.1.

use axum::extract::rejection::JsonRejection;
use axum::http::StatusCode;
use axum::http::header::CONTENT_TYPE;
use axum::response::{Html, IntoResponse, Response};
use axum::routing::{MethodRouter, delete, get, patch, post, put};
use axum::{Json, Router};
use serde_json::json;

use crate::generated_contract::{OPENAPI_JSON, REST_SAY_METHOD, REST_SAY_PATH};
use crate::logic::generate_reply;
use crate::proto::chat::v1::{SayRequest, SayResponse};

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

pub fn router() -> Router {
    let say_route: MethodRouter = match REST_SAY_METHOD {
        "GET" => get(chat_service_say),
        "PUT" => put(chat_service_say),
        "DELETE" => delete(chat_service_say),
        "PATCH" => patch(chat_service_say),
        _ => post(chat_service_say),
    };

    Router::new()
        .route(REST_SAY_PATH, say_route)
        .route("/api/health", get(health))
        .route("/openapi.json", get(openapi_json))
        .route("/docs", get(docs))
}

async fn chat_service_say(payload: Result<Json<SayRequest>, JsonRejection>) -> Response {
    let Json(body) = match payload {
        Ok(json) => json,
        Err(rejection) => {
            return (
                StatusCode::UNPROCESSABLE_ENTITY,
                Json(json!({ "detail": rejection.body_text() })),
            )
                .into_response();
        }
    };

    if body.text.trim().is_empty() {
        return (
            StatusCode::UNPROCESSABLE_ENTITY,
            Json(json!({ "detail": "text must be nonempty" })),
        )
            .into_response();
    }

    let reply = generate_reply(&body.text).to_string();
    (StatusCode::OK, Json(SayResponse { reply })).into_response()
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
