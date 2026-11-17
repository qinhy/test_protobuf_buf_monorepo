use chat_backend::logic::{REPLY, generate_reply};

#[test]
fn reply_is_constant() {
    assert_eq!(generate_reply("hello"), REPLY);
    assert_eq!(generate_reply("another request"), REPLY);
}
