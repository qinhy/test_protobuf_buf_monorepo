//! Standalone Rust backend CLI entry point: `cargo run` / `chat-server`.
//!
//! REST /docs and /api/chat:          HTTP/1.1 on port 8000 (HOST:PORT)
//! Connect /chat.v1.ChatService/Say: HTTP/1.1 on port 8000 (HOST:PORT)
//! Native gRPC:                      HTTP/2 h2c on port 50051 (GRPC_BIND)

use std::env;
use std::error::Error;

use chat_backend::app::{serve_grpc_with_shutdown, serve_http_with_shutdown};
use tokio::net::TcpListener;
use tokio::sync::watch;

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let host = env::var("HOST").unwrap_or_else(|_| "127.0.0.1".to_string());
    let port = env::var("PORT").unwrap_or_else(|_| "8000".to_string());
    let http_addr = format!("{host}:{port}");
    let grpc_addr = env::var("GRPC_BIND").unwrap_or_else(|_| "127.0.0.1:50051".to_string());

    let http_listener = TcpListener::bind(&http_addr).await?;
    let grpc_listener = TcpListener::bind(&grpc_addr).await?;

    println!("[http] REST + ConnectRPC listening at http://{http_addr}");
    println!("[grpc] native HTTP/2 (h2c) listening at {grpc_addr}");

    let (shutdown_tx, mut http_rx) = watch::channel(false);
    let mut grpc_rx = shutdown_tx.subscribe();

    tokio::spawn(async move {
        let _ = tokio::signal::ctrl_c().await;
        let _ = shutdown_tx.send(true);
    });

    let (http_res, grpc_res) = tokio::join!(
        serve_http_with_shutdown(http_listener, async move {
            let _ = http_rx.changed().await;
        }),
        serve_grpc_with_shutdown(grpc_listener, async move {
            let _ = grpc_rx.changed().await;
        }),
    );

    http_res?;
    grpc_res?;
    Ok(())
}
