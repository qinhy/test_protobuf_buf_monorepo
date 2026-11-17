use axum::body::Body;
use axum::http::header::{ACCESS_CONTROL_ALLOW_ORIGIN, CONTENT_TYPE, ORIGIN};
use axum::http::{Request, StatusCode};
use chat_backend::app::{http_router, serve_grpc_with_shutdown};
use chat_backend::logic::REPLY;
use chat_backend::proto::chat::v1::chat_service_client::ChatServiceClient;
use chat_backend::proto::chat::v1::{ChatEvent, SayRequest, SayResponse, chat_event::Payload};
use prost::Message as _;
use serde_json::{Value, json};
use tokio::net::TcpListener;
use tokio::sync::oneshot;
use tower::ServiceExt as _;

async fn body_bytes(response: axum::response::Response) -> Vec<u8> {
    axum::body::to_bytes(response.into_body(), usize::MAX)
        .await
        .expect("read response body")
        .to_vec()
}

fn encode_connect_frame(flags: u8, payload: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(5 + payload.len());
    out.push(flags);
    out.extend_from_slice(&(payload.len() as u32).to_be_bytes());
    out.extend_from_slice(payload);
    out
}

fn decode_connect_frames(bytes: &[u8]) -> Vec<(u8, Vec<u8>)> {
    let mut frames = Vec::new();
    let mut offset = 0;
    while offset < bytes.len() {
        assert!(offset + 5 <= bytes.len(), "truncated frame header");
        let flags = bytes[offset];
        let len = u32::from_be_bytes([
            bytes[offset + 1],
            bytes[offset + 2],
            bytes[offset + 3],
            bytes[offset + 4],
        ]) as usize;
        offset += 5;
        assert!(offset + len <= bytes.len(), "truncated frame payload");
        frames.push((flags, bytes[offset..offset + len].to_vec()));
        offset += len;
    }
    frames
}

#[tokio::test]
async fn rest_and_connect_endpoints() {
    let app = http_router();

    // REST POST /api/chat -> 200
    let res = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/chat")
                .header(CONTENT_TYPE, "application/json")
                .header(ORIGIN, "http://localhost:5173")
                .body(Body::from(r#"{"text":"rest"}"#))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(res.status(), StatusCode::OK);
    assert_eq!(
        res.headers()
            .get(ACCESS_CONTROL_ALLOW_ORIGIN)
            .and_then(|v| v.to_str().ok()),
        Some("http://localhost:5173")
    );
    let json_body: Value = serde_json::from_slice(&body_bytes(res).await).unwrap();
    assert_eq!(json_body["reply"], REPLY);

    // REST POST /api/chat/stream -> 200 NDJSON
    let stream_res = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/chat/stream")
                .header(CONTENT_TYPE, "application/json")
                .header("accept", "application/x-ndjson")
                .body(Body::from(r#"{"text":"stream"}"#))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(stream_res.status(), StatusCode::OK);
    assert_eq!(
        stream_res
            .headers()
            .get(CONTENT_TYPE)
            .and_then(|v| v.to_str().ok()),
        Some("application/x-ndjson")
    );
    let ndjson_raw = String::from_utf8(body_bytes(stream_res).await).unwrap();
    let ndjson_events: Vec<Value> = ndjson_raw
        .lines()
        .filter(|line| !line.trim().is_empty())
        .map(|line| serde_json::from_str::<Value>(line).unwrap()["result"].clone())
        .collect();
    assert!(ndjson_events[0].get("start").is_some());
    let ndjson_deltas: String = ndjson_events
        .iter()
        .filter_map(|e| e.get("delta")?.get("text")?.as_str())
        .collect();
    assert_eq!(ndjson_deltas, REPLY);
    assert_eq!(
        ndjson_events.last().unwrap()["complete"]["reply"],
        REPLY
    );

    // REST POST /api/chat & /api/chat/stream whitespace/empty/null -> 422
    for uri in ["/api/chat", "/api/chat/stream"] {
        for invalid in [r#"{"text":"   "}"#, r#"{}"#, r#"{"text":null}"#] {
            let res = app
                .clone()
                .oneshot(
                    Request::builder()
                        .method("POST")
                        .uri(uri)
                        .header(CONTENT_TYPE, "application/json")
                        .body(Body::from(invalid))
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(res.status(), StatusCode::UNPROCESSABLE_ENTITY, "uri: {uri} payload: {invalid}");
        }
    }

    // Health, Swagger /docs, and /openapi.json
    let health = app
        .clone()
        .oneshot(Request::builder().uri("/api/health").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(health.status(), StatusCode::OK);
    let health_json: Value = serde_json::from_slice(&body_bytes(health).await).unwrap();
    assert_eq!(health_json, json!({ "status": "ok" }));

    let docs = app
        .clone()
        .oneshot(Request::builder().uri("/docs").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(docs.status(), StatusCode::OK);
    let docs_html = String::from_utf8(body_bytes(docs).await).unwrap();
    assert!(docs_html.contains("/openapi.json"));

    let openapi = app
        .clone()
        .oneshot(Request::builder().uri("/openapi.json").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(openapi.status(), StatusCode::OK);
    let spec: Value = serde_json::from_slice(&body_bytes(openapi).await).unwrap();
    assert!(spec["paths"].get("/api/chat").is_some());
    assert!(
        spec["paths"]["/api/chat/stream"]["post"]["responses"]["200"]["content"]
            .get("application/x-ndjson")
            .is_some()
    );

    // ConnectRPC JSON unary
    let connect_json = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/chat.v1.ChatService/Say")
                .header(CONTENT_TYPE, "application/json")
                .body(Body::from(r#"{"text":"connect"}"#))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(connect_json.status(), StatusCode::OK);
    let connect_body: Value = serde_json::from_slice(&body_bytes(connect_json).await).unwrap();
    assert_eq!(connect_body["reply"], REPLY);

    // ConnectRPC binary Protobuf unary
    let payload = SayRequest {
        text: "binary".to_string(),
    }
    .encode_to_vec();
    let connect_proto = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/chat.v1.ChatService/Say")
                .header(CONTENT_TYPE, "application/proto")
                .header("accept", "application/proto")
                .body(Body::from(payload.clone()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(connect_proto.status(), StatusCode::OK);
    let decoded = SayResponse::decode(body_bytes(connect_proto).await.as_slice()).unwrap();
    assert_eq!(decoded.reply, REPLY);

    // ConnectRPC binary streaming
    let connect_stream_proto = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/chat.v1.ChatService/StreamSay")
                .header(CONTENT_TYPE, "application/connect+proto")
                .body(Body::from(encode_connect_frame(0, &payload)))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(connect_stream_proto.status(), StatusCode::OK);
    let frames = decode_connect_frames(&body_bytes(connect_stream_proto).await);
    assert!(frames.len() >= 3);
    assert_eq!(frames.last().unwrap().0, 0x02);
    let events: Vec<ChatEvent> = frames[..frames.len() - 1]
        .iter()
        .map(|(flags, data)| {
            assert_eq!(*flags, 0);
            ChatEvent::decode(data.as_slice()).unwrap()
        })
        .collect();
    let stream_deltas: String = events
        .iter()
        .filter_map(|e| match &e.payload {
            Some(Payload::Delta(d)) => Some(d.text.as_str()),
            _ => None,
        })
        .collect();
    assert_eq!(stream_deltas, REPLY);
    assert!(matches!(
        &events.last().unwrap().payload,
        Some(Payload::Complete(c)) if c.reply == REPLY
    ));

    // ConnectRPC JSON streaming
    let connect_stream_json = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/chat.v1.ChatService/StreamSay")
                .header(CONTENT_TYPE, "application/connect+json")
                .body(Body::from(encode_connect_frame(0, br#"{"text":"connect-stream"}"#)))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(connect_stream_json.status(), StatusCode::OK);
    let json_frames = decode_connect_frames(&body_bytes(connect_stream_json).await);
    assert_eq!(json_frames.last().unwrap().0, 0x02);

    // ConnectRPC unsupported content-type -> 415
    let unsupported = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/chat.v1.ChatService/Say")
                .header(CONTENT_TYPE, "text/plain")
                .body(Body::from("hi"))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(unsupported.status(), StatusCode::UNSUPPORTED_MEDIA_TYPE);
}

#[tokio::test]
async fn native_grpc_endpoint() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    let (tx, rx) = oneshot::channel::<()>();

    let server_task = tokio::spawn(async move {
        serve_grpc_with_shutdown(listener, async {
            let _ = rx.await;
        })
        .await
        .unwrap();
    });

    let endpoint = format!("http://{addr}");
    let mut client = ChatServiceClient::connect(endpoint).await.unwrap();
    let response = client
        .say(SayRequest {
            text: "grpc".to_string(),
        })
        .await
        .unwrap()
        .into_inner();
    assert_eq!(response.reply, REPLY);

    let mut stream = client
        .stream_say(SayRequest {
            text: "grpc-stream".to_string(),
        })
        .await
        .unwrap()
        .into_inner();
    let mut events = Vec::new();
    while let Some(event) = stream.message().await.unwrap() {
        events.push(event);
    }
    let deltas: String = events
        .iter()
        .filter_map(|e| match &e.payload {
            Some(Payload::Delta(d)) => Some(d.text.as_str()),
            _ => None,
        })
        .collect();
    assert_eq!(deltas, REPLY);
    assert!(matches!(
        &events.last().unwrap().payload,
        Some(Payload::Complete(c)) if c.reply == REPLY
    ));

    let _ = tx.send(());
    server_task.await.unwrap();
}
