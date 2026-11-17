//! The one place where the chat business logic lives.

use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

use tokio::sync::mpsc;

use crate::events::ChatDomainEvent;

pub const REPLY: &str = "Hello! I'm a demo AI assistant. This is a constant reply.";

static NEXT_MESSAGE_SEQ: AtomicU64 = AtomicU64::new(1);

fn next_message_id() -> String {
    let id = NEXT_MESSAGE_SEQ.fetch_add(1, Ordering::Relaxed);
    format!("msg-{id:06}")
}

/// Replace this function (and `stream_reply`) with an LLM call when ready.
pub fn generate_reply(_text: &str) -> &'static str {
    // The input is deliberately unused by this constant-reply demo.
    REPLY
}

/// Stream transport-neutral chat events into `tx`. Stops early if the receiver drops.
pub async fn stream_reply_with_options(
    _text: &str,
    tx: mpsc::Sender<ChatDomainEvent>,
    chunk_chars: usize,
    delay: Duration,
) {
    let mut sequence = 1u32;
    if tx
        .send(ChatDomainEvent::Started {
            sequence,
            message_id: next_message_id(),
        })
        .await
        .is_err()
    {
        return;
    }

    let step = chunk_chars.max(1);
    let mut chars = REPLY.chars();
    loop {
        let chunk: String = chars.by_ref().take(step).collect();
        if chunk.is_empty() {
            break;
        }
        if !delay.is_zero() {
            tokio::time::sleep(delay).await;
        }
        sequence += 1;
        if tx
            .send(ChatDomainEvent::Delta {
                sequence,
                text: chunk,
            })
            .await
            .is_err()
        {
            return;
        }
    }

    sequence += 1;
    let _ = tx
        .send(ChatDomainEvent::Completed {
            sequence,
            reply: REPLY.to_string(),
        })
        .await;
}

/// Default demo stream: 4-character chunks with 50 ms pacing.
pub async fn stream_reply(text: &str, tx: mpsc::Sender<ChatDomainEvent>) {
    stream_reply_with_options(text, tx, 4, Duration::from_millis(50)).await;
}

/// Consume `stream_reply` and return the final reply for unary callers.
pub async fn complete_reply(text: &str) -> Result<String, String> {
    let (tx, mut rx) = mpsc::channel(16);
    stream_reply_with_options(text, tx, 4, Duration::ZERO).await;

    let mut final_reply = None;
    while let Some(event) = rx.recv().await {
        match event {
            ChatDomainEvent::Completed { reply, .. } => final_reply = Some(reply),
            ChatDomainEvent::Failed { code, message, .. } => {
                return Err(format!("{code}: {message}"));
            }
            ChatDomainEvent::Started { .. } | ChatDomainEvent::Delta { .. } => {}
        }
    }
    final_reply.ok_or_else(|| "Chat stream ended without a completion event".to_string())
}
