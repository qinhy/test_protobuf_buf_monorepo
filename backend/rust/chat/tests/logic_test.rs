use std::time::Duration;

use chat_backend::events::ChatDomainEvent;
use chat_backend::logic::{REPLY, complete_reply, generate_reply, stream_reply_with_options};
use tokio::sync::mpsc;

#[test]
fn reply_is_constant() {
    assert_eq!(generate_reply("hello"), REPLY);
    assert_eq!(generate_reply("another request"), REPLY);
}

#[tokio::test]
async fn stream_reply_emits_ordered_events_and_matches_complete_reply() {
    let (tx, mut rx) = mpsc::channel(32);
    stream_reply_with_options("hello", tx, 4, Duration::ZERO).await;

    let mut events = Vec::new();
    while let Some(event) = rx.recv().await {
        events.push(event);
    }

    assert!(events.len() >= 3);
    for (idx, event) in events.iter().enumerate() {
        assert_eq!(event.sequence(), (idx + 1) as u32);
    }
    assert!(matches!(events.first(), Some(ChatDomainEvent::Started { .. })));

    let deltas: String = events
        .iter()
        .filter_map(|event| match event {
            ChatDomainEvent::Delta { text, .. } => Some(text.as_str()),
            _ => None,
        })
        .collect();
    assert_eq!(deltas, REPLY);

    assert!(matches!(
        events.last(),
        Some(ChatDomainEvent::Completed { reply, .. }) if reply == REPLY
    ));

    assert_eq!(complete_reply("hello").await.unwrap(), REPLY);
}
