//! Native gRPC (`tonic`) and ConnectRPC (unary + server-streaming) adapters.
//!
//! No REST/Connect/gRPC handler contains independent chat logic.

use std::convert::Infallible;

use axum::Router;
use axum::body::{Body, Bytes};
use axum::http::header::{CONTENT_ENCODING, CONTENT_TYPE};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response as HttpResponse};
use axum::routing::post;
use prost::Message as _;
use serde_json::json;
use tokio::sync::mpsc;
use tokio_stream::wrappers::ReceiverStream;
use tonic::{Request, Response, Status};

use crate::generated_contract::{CONNECT_SAY_PATH, CONNECT_STREAM_SAY_PATH};
use crate::logic::{complete_reply, stream_reply};
use crate::proto::chat::v1::chat_service_server::ChatService;
use crate::proto::chat::v1::{ChatEvent, SayRequest, SayResponse};
use crate::serialization::{to_proto, to_proto_json_value};

const CONNECT_FLAG_END_STREAM: u8 = 0x02;

#[derive(Debug, Default, Clone, Copy)]
pub struct GrpcChatService;

#[tonic::async_trait]
impl ChatService for GrpcChatService {
    type StreamSayStream = ReceiverStream<Result<ChatEvent, Status>>;

    async fn say(
        &self,
        request: Request<SayRequest>,
    ) -> Result<Response<SayResponse>, Status> {
        let req = request.into_inner();
        let reply = complete_reply(&req.text)
            .await
            .map_err(Status::internal)?;
        Ok(Response::new(SayResponse { reply }))
    }

    async fn stream_say(
        &self,
        request: Request<SayRequest>,
    ) -> Result<Response<Self::StreamSayStream>, Status> {
        let req = request.into_inner();
        let (domain_tx, mut domain_rx) = mpsc::channel(16);
        let (grpc_tx, grpc_rx) = mpsc::channel(16);

        tokio::spawn(async move {
            stream_reply(&req.text, domain_tx).await;
        });

        tokio::spawn(async move {
            while let Some(event) = domain_rx.recv().await {
                if grpc_tx.send(Ok(to_proto(&event))).await.is_err() {
                    break;
                }
            }
        });

        Ok(Response::new(ReceiverStream::new(grpc_rx)))
    }
}

pub fn connect_router() -> Router {
    Router::new()
        .route(CONNECT_SAY_PATH, post(connect_say))
        .route(CONNECT_STREAM_SAY_PATH, post(connect_stream_say))
}

fn connect_error(status: StatusCode, code: &str, message: impl Into<String>) -> HttpResponse {
    let body = serde_json::to_vec(&json!({
        "code": code,
        "message": message.into(),
    }))
    .unwrap_or_else(|_| b"{\"code\":\"internal\",\"message\":\"serialization error\"}".to_vec());
    (status, [(CONTENT_TYPE, "application/json")], body).into_response()
}

fn media_type(headers: &HeaderMap) -> Option<String> {
    headers
        .get(CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .map(|raw| raw.split(';').next().unwrap_or("").trim().to_ascii_lowercase())
}

fn validate_content_encoding(headers: &HeaderMap) -> Result<(), HttpResponse> {
    if let Some(encoding) = headers.get(CONTENT_ENCODING).and_then(|v| v.to_str().ok()) {
        if !encoding.trim().eq_ignore_ascii_case("identity") {
            return Err(connect_error(
                StatusCode::UNSUPPORTED_MEDIA_TYPE,
                "unimplemented",
                format!("unsupported content-encoding: {encoding}"),
            ));
        }
    }
    Ok(())
}

fn encode_connect_frame(flags: u8, payload: &[u8]) -> Bytes {
    let mut frame = Vec::with_capacity(5 + payload.len());
    frame.push(flags);
    frame.extend_from_slice(&(payload.len() as u32).to_be_bytes());
    frame.extend_from_slice(payload);
    Bytes::from(frame)
}

fn decode_connect_frame(body: &[u8]) -> Result<(u8, &[u8]), String> {
    if body.len() < 5 {
        return Err("truncated connect envelope header".to_string());
    }
    let flags = body[0];
    let len = u32::from_be_bytes([body[1], body[2], body[3], body[4]]) as usize;
    if body.len() != 5 + len {
        return Err(format!(
            "connect frame length mismatch: expected {}, got {}",
            5 + len,
            body.len()
        ));
    }
    Ok((flags, &body[5..]))
}

async fn connect_say(headers: HeaderMap, body: Bytes) -> HttpResponse {
    if let Err(err_response) = validate_content_encoding(&headers) {
        return err_response;
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
            let reply = match complete_reply(&req.text).await {
                Ok(reply) => reply,
                Err(err) => return connect_error(StatusCode::INTERNAL_SERVER_ERROR, "internal", err),
            };
            let resp = SayResponse { reply };
            match serde_json::to_vec(&resp) {
                Ok(bytes) => (StatusCode::OK, [(CONTENT_TYPE, "application/json")], bytes).into_response(),
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
            let reply = match complete_reply(&req.text).await {
                Ok(reply) => reply,
                Err(err) => return connect_error(StatusCode::INTERNAL_SERVER_ERROR, "internal", err),
            };
            let resp = SayResponse { reply };
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

async fn connect_stream_say(headers: HeaderMap, body: Bytes) -> HttpResponse {
    if let Err(err_response) = validate_content_encoding(&headers) {
        return err_response;
    }

    let (response_content_type, is_binary) = match media_type(&headers).as_deref() {
        Some("application/connect+proto") => ("application/connect+proto", true),
        Some("application/connect+protobuf") => ("application/connect+protobuf", true),
        Some("application/connect+json") => ("application/connect+json", false),
        Some(other) => {
            return connect_error(
                StatusCode::UNSUPPORTED_MEDIA_TYPE,
                "unimplemented",
                format!("unsupported streaming content-type: {other}"),
            );
        }
        None => {
            return connect_error(
                StatusCode::UNSUPPORTED_MEDIA_TYPE,
                "unimplemented",
                "missing content-type header",
            );
        }
    };

    let (flags, payload) = match decode_connect_frame(&body) {
        Ok(parts) => parts,
        Err(err) => {
            return connect_error(StatusCode::BAD_REQUEST, "invalid_argument", err);
        }
    };
    if flags != 0 {
        return connect_error(
            StatusCode::UNSUPPORTED_MEDIA_TYPE,
            "unimplemented",
            format!("unsupported connect frame flags: {flags}"),
        );
    }

    let req = if is_binary {
        match SayRequest::decode(payload) {
            Ok(req) => req,
            Err(err) => {
                return connect_error(
                    StatusCode::BAD_REQUEST,
                    "invalid_argument",
                    format!("invalid protobuf request: {err}"),
                );
            }
        }
    } else {
        match serde_json::from_slice::<SayRequest>(payload) {
            Ok(req) => req,
            Err(err) => {
                return connect_error(
                    StatusCode::BAD_REQUEST,
                    "invalid_argument",
                    format!("invalid JSON request: {err}"),
                );
            }
        }
    };

    let (domain_tx, mut domain_rx) = mpsc::channel(16);
    let (frame_tx, frame_rx) = mpsc::channel::<Result<Bytes, Infallible>>(16);
    let text = req.text;

    tokio::spawn(async move {
        stream_reply(&text, domain_tx).await;
    });

    tokio::spawn(async move {
        while let Some(event) = domain_rx.recv().await {
            let encoded = if is_binary {
                to_proto(&event).encode_to_vec()
            } else {
                serde_json::to_vec(&to_proto_json_value(&event)).unwrap_or_default()
            };
            if frame_tx
                .send(Ok(encode_connect_frame(0, &encoded)))
                .await
                .is_err()
            {
                return;
            }
        }
        let _ = frame_tx
            .send(Ok(encode_connect_frame(CONNECT_FLAG_END_STREAM, b"{}")))
            .await;
    });

    (
        StatusCode::OK,
        [(CONTENT_TYPE, response_content_type)],
        Body::from_stream(ReceiverStream::new(frame_rx)),
    )
        .into_response()
}
