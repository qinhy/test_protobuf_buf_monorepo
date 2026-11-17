//! Application assembly for REST + ConnectRPC (HTTP/1.1) and native gRPC (HTTP/2 h2c).

use axum::Router;
use axum::http::{HeaderValue, Method};
use tokio::net::TcpListener;
use tonic::service::Routes;
use tower_http::cors::{Any, CorsLayer};

use crate::proto::chat::v1::chat_service_server::ChatServiceServer;
use crate::rest;
use crate::service::{self, GrpcChatService};

pub fn http_router() -> Router {
    let cors = CorsLayer::new()
        .allow_origin([
            HeaderValue::from_static("http://localhost:5173"),
            HeaderValue::from_static("http://127.0.0.1:5173"),
        ])
        .allow_credentials(false)
        .allow_methods([Method::POST, Method::GET, Method::OPTIONS])
        .allow_headers(Any);

    // REST routes are registered before ConnectRPC routes, matching the Python backend.
    Router::new()
        .merge(rest::router())
        .merge(service::connect_router())
        .layer(cors)
}

pub fn grpc_routes() -> Routes {
    Routes::new(ChatServiceServer::new(GrpcChatService))
}

pub async fn serve_http_with_shutdown<F>(
    listener: TcpListener,
    shutdown: F,
) -> std::io::Result<()>
where
    F: std::future::Future<Output = ()> + Send + 'static,
{
    axum::serve(listener, http_router())
        .with_graceful_shutdown(shutdown)
        .await
}

pub async fn serve_grpc_with_shutdown<F>(
    listener: TcpListener,
    shutdown: F,
) -> Result<(), tonic::transport::Error>
where
    F: std::future::Future<Output = ()> + Send + 'static,
{
    let incoming = tonic::transport::server::TcpIncoming::from(listener);
    tonic::transport::Server::builder()
        .add_routes(grpc_routes())
        .serve_with_incoming_shutdown(incoming, shutdown)
        .await
}
