//! Transport-neutral domain event types shared across REST, ConnectRPC, and gRPC.

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ChatDomainEvent {
    Started {
        sequence: u32,
        message_id: String,
    },
    Delta {
        sequence: u32,
        text: String,
    },
    Completed {
        sequence: u32,
        reply: String,
    },
    Failed {
        sequence: u32,
        code: String,
        message: String,
    },
}

impl ChatDomainEvent {
    pub fn sequence(&self) -> u32 {
        match self {
            Self::Started { sequence, .. }
            | Self::Delta { sequence, .. }
            | Self::Completed { sequence, .. }
            | Self::Failed { sequence, .. } => *sequence,
        }
    }
}
