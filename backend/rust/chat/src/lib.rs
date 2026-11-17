pub mod app;
pub mod logic;
pub mod rest;
pub mod service;

pub mod generated_contract {
    include!(concat!(env!("OUT_DIR"), "/rest_generated.rs"));
}

pub mod proto {
    pub mod chat {
        pub mod v1 {
            tonic::include_proto!("chat.v1");
        }
    }
}
