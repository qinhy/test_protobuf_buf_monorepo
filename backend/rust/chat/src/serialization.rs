//! Serializers mapping domain `ChatDomainEvent` values to Protobuf or NDJSON.

use serde_json::json;

use crate::events::ChatDomainEvent;
use crate::proto::chat::v1::{
    ChatComplete, ChatDelta, ChatEvent, ChatFailure, ChatStart, chat_event::Payload,
};

pub fn to_proto(event: &ChatDomainEvent) -> ChatEvent {
    match event {
        ChatDomainEvent::Started {
            sequence,
            message_id,
        } => ChatEvent {
            sequence: *sequence,
            payload: Some(Payload::Start(ChatStart {
                message_id: message_id.clone(),
            })),
        },
        ChatDomainEvent::Delta { sequence, text } => ChatEvent {
            sequence: *sequence,
            payload: Some(Payload::Delta(ChatDelta { text: text.clone() })),
        },
        ChatDomainEvent::Completed { sequence, reply } => ChatEvent {
            sequence: *sequence,
            payload: Some(Payload::Complete(ChatComplete {
                reply: reply.clone(),
            })),
        },
        ChatDomainEvent::Failed {
            sequence,
            code,
            message,
        } => ChatEvent {
            sequence: *sequence,
            payload: Some(Payload::Failure(ChatFailure {
                code: code.clone(),
                message: message.clone(),
            })),
        },
    }
}

pub fn to_proto_json_value(event: &ChatDomainEvent) -> serde_json::Value {
    match event {
        ChatDomainEvent::Started {
            sequence,
            message_id,
        } => json!({
            "sequence": sequence,
            "start": { "messageId": message_id },
        }),
        ChatDomainEvent::Delta { sequence, text } => json!({
            "sequence": sequence,
            "delta": { "text": text },
        }),
        ChatDomainEvent::Completed { sequence, reply } => json!({
            "sequence": sequence,
            "complete": { "reply": reply },
        }),
        ChatDomainEvent::Failed {
            sequence,
            code,
            message,
        } => json!({
            "sequence": sequence,
            "failure": { "code": code, "message": message },
        }),
    }
}

pub fn to_ndjson_line(event: &ChatDomainEvent) -> Vec<u8> {
    let mut bytes = serde_json::to_vec(&json!({ "result": to_proto_json_value(event) }))
        .unwrap_or_else(|_| b"{\"error\":{\"code\":13,\"message\":\"serialization error\"}}".to_vec());
    bytes.push(b'\n');
    bytes
}

pub fn ndjson_error_line(code: i32, message: &str) -> Vec<u8> {
    let mut bytes = serde_json::to_vec(&json!({
        "error": { "code": code, "message": message }
    }))
    .unwrap_or_else(|_| b"{\"error\":{\"code\":13,\"message\":\"internal error\"}}".to_vec());
    bytes.push(b'\n');
    bytes
}
