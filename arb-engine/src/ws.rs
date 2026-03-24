use crate::types::{to_price_key, OrderBook, PriceLevel, WsMessage};
use futures_util::{SinkExt, StreamExt};
use serde_json::json;
use tokio::sync::mpsc;
use tokio_tungstenite::{connect_async, tungstenite::Message};
use tracing::{error, info, warn};

pub enum BookEvent {
    Snapshot(OrderBook),
    Update { token_id: String, bids: Vec<PriceLevel>, asks: Vec<PriceLevel> },
}

pub async fn connect_and_stream(
    ws_url: String,
    token_ids: Vec<String>,
    tx: mpsc::Sender<BookEvent>,
) {
    loop {
        match run_connection(&ws_url, &token_ids, &tx).await {
            Ok(()) => warn!("WebSocket closed, reconnecting in 2s..."),
            Err(e) => error!("WebSocket error: {}, reconnecting in 2s...", e),
        }
        tokio::time::sleep(std::time::Duration::from_secs(2)).await;
    }
}

async fn run_connection(
    ws_url: &str,
    token_ids: &[String],
    tx: &mpsc::Sender<BookEvent>,
) -> Result<(), Box<dyn std::error::Error>> {
    let (ws_stream, _) = connect_async(ws_url).await?;
    let (mut write, mut read) = ws_stream.split();

    info!("WebSocket connected, subscribing to {} tokens", token_ids.len());

    let sub = json!({
        "assets_ids": token_ids,
        "type": "market",
    });
    write.send(Message::Text(sub.to_string().into())).await?;

    let ping_handle = tokio::spawn({
        let mut write = write;
        async move {
            loop {
                tokio::time::sleep(std::time::Duration::from_secs(10)).await;
                if write.send(Message::Text("PING".into())).await.is_err() {
                    break;
                }
            }
        }
    });

    while let Some(msg) = read.next().await {
        let msg = msg?;
        match msg {
            Message::Text(text) => {
                if text == "PONG" {
                    continue;
                }
                if let Err(e) = handle_message(&text, tx).await {
                    warn!("Failed to process message: {}", e);
                }
            }
            Message::Close(_) => break,
            _ => {}
        }
    }

    ping_handle.abort();
    Ok(())
}

async fn handle_message(
    text: &str,
    tx: &mpsc::Sender<BookEvent>,
) -> Result<(), Box<dyn std::error::Error>> {
    let msgs: Vec<WsMessage> = match serde_json::from_str(text) {
        Ok(v) => v,
        Err(_) => {
            if let Ok(single) = serde_json::from_str::<WsMessage>(text) {
                vec![single]
            } else {
                return Ok(());
            }
        }
    };

    for msg in msgs {
        match msg.event_type.as_str() {
            "book" => {
                let mut book = OrderBook::new(msg.asset_id.clone());
                if let Some(bids) = &msg.bids {
                    for level in bids {
                        let price: f64 = level.price.parse().unwrap_or(0.0);
                        let size: f64 = level.size.parse().unwrap_or(0.0);
                        if size > 0.0 {
                            book.bids.insert(to_price_key(price), size);
                        }
                    }
                }
                if let Some(asks) = &msg.asks {
                    for level in asks {
                        let price: f64 = level.price.parse().unwrap_or(0.0);
                        let size: f64 = level.size.parse().unwrap_or(0.0);
                        if size > 0.0 {
                            book.asks.insert(to_price_key(price), size);
                        }
                    }
                }
                let _ = tx.send(BookEvent::Snapshot(book)).await;
            }
            "price_change" => {
                let bids = msg.bids.unwrap_or_default();
                let asks = msg.asks.unwrap_or_default();
                let _ = tx.send(BookEvent::Update {
                    token_id: msg.asset_id,
                    bids,
                    asks,
                }).await;
            }
            _ => {}
        }
    }

    Ok(())
}
