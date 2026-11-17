//! The one place where the chat business logic lives.

pub const REPLY: &str = "Hello! I'm a demo AI assistant. This is a constant reply.";

/// Replace this function with an LLM call when ready.
pub fn generate_reply(_text: &str) -> &'static str {
    // The input is deliberately unused by this constant-reply demo.
    REPLY
}
