//! Native gRPC (`tonic`) and ConnectRPC adapters.
//!
//! No REST/Connect/gRPC handler contains independent chat logic.

use axum::Router;
use axum::body::Bytes;
use axum::http::header::{CONTENT_ENCODING, CONTENT_TYPE};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response as HttpResponse};
use axum::routing::post;
use prost::Message as _;
use serde_json::json;
use tonic::{Request, Response, Status};

use crate::generated_contract::CONNECT_SAY_PATH;
use crate::logic::generate_reply;
use crate::proto::chat::v1::chat_service_server::ChatService;
use crate::proto::chat::v1::{SayRequest, SayResponse};

#[derive(Debug, Default, Clone, Copy)]
pub struct GrpcChatService;

#[tonic::async_trait]
impl ChatService for GrpcChatService {
    async fn say(
        &self,
        request: Request<SayRequest>,
    ) -> Result<Response<SayResponse>, Status> {
        let req = request.into_inner();
        let reply = generate_reply(&req.text).to_string();
        Ok(Response::new(SayResponse { reply }))
    }
}

pub fn connect_router() -> Router {
    Router::new().route(CONNECT_SAY_PATH, post(connect_say))
}

fn connect_error(status: StatusCode, code: &str, message: impl Into<String>) -> HttpResponse {
    let body = serde_json::to_vec(&json!({
        "code": code,
        "message": message.into(),
    }))
    .unwrap_or_else(|_| b"{\"code\":\"internal\",\"message\":\"serialization error\"}".to_vec());
    (
        status,
        [(CONTENT_TYPE, "application/json")],
        body,
    )
        .into_response()
}

fn media_type(headers: &HeaderMap) -> Option<String> {
    headers
        .get(CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .map(|raw| raw.split(';').next().unwrap_or("").trim().to_ascii_lowercase())
}

async fn connect_say(headers: HeaderMap, body: Bytes) -> HttpResponse {
    if let Some(encoding) = headers.get(CONTENT_ENCODING).and_then(|v| v.to_str().ok()) {
        if !encoding.trim().eq_ignore_ascii_case("identity") {
            return connect_error(
                StatusCode::UNSUPPORTED_MEDIA_TYPE,
                "unimplemented",
                format!("unsupported content-encoding: {encoding}"),
            );
        }
    }

    match media_type(&headers).as_deref() {
        Some("application/json") => {
            let req: SayRequest = match serde_json::from_slice(&body) {
                Ok(req) => req,
                Err(err) => {
                    return connect_error(
                        StatusCode::BAD_REQUEST,
                        "invalid_argument",
                        format!("invalid JSON request: {err}"),
                    );
                }
            };
            let resp = SayResponse {
                reply: generate_reply(&req.text).to_string(),
            };
            match serde_json::to_vec(&resp) {
                Ok(bytes) => (
                    StatusCode::OK,
                    [(CONTENT_TYPE, "application/json")],
                    bytes,
                )
                    .into_response(),
                Err(err) => connect_error(
                    StatusCode::INTERNAL_SERVER_ERROR,
                    "internal",
                    format!("failed to encode response: {err}"),
                ),
            }
        }
        Some("application/proto") | Some("application/protobuf") => {
            let req = match SayRequest::decode(body) {
                Ok(req) => req,
                Err(err) => {
                    return connect_error(
                        StatusCode::BAD_REQUEST,
                        "invalid_argument",
                        format!("invalid protobuf request: {err}"),
                    );
                }
            };
            let resp = SayResponse {
                reply: generate_reply(&req.text).to_string(),
            };
            (
                StatusCode::OK,
                [(CONTENT_TYPE, "application/proto")],
                resp.encode_to_vec(),
            )
                .into_response()
        }
        Some(other) => connect_error(
            StatusCode::UNSUPPORTED_MEDIA_TYPE,
            "unimplemented",
            format!("unsupported content-type: {other}"),
        ),
        None => connect_error(
            StatusCode::UNSUPPORTED_MEDIA_TYPE,
            "unimplemented",
            "missing content-type header",
        ),
    }
}
