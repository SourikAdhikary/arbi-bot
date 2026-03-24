mod config;
mod executor;
mod markets;
mod scanner;
mod types;
mod ws;

use config::Config;
use executor::ArbExecutor;
use scanner::ArbScanner;
use tokio::sync::mpsc;
use tracing::{info, warn};

#[tokio::main]
async fn main() {
    dotenvy::from_filename("../.env").ok();
    dotenvy::dotenv().ok();

    tracing_subscriber::fmt()
        .with_env_filter("arb_engine=debug")
        .with_target(false)
        .init();

    let config = Config::from_env();
    info!("=== Polymarket Arb Engine (Rust) ===");
    info!(
        "bankroll=${:.2} | min_spread={:.2}% | max_position=${:.2} | dry_run={}",
        config.bankroll_usdc, config.min_arb_spread_pct, config.max_position_usdc, config.dry_run
    );

    info!("Fetching binary markets from Gamma API...");
    let market_pairs = markets::fetch_binary_markets(&config.gamma_url, 500).await;

    if market_pairs.is_empty() {
        warn!("No binary markets found, exiting");
        return;
    }

    let token_ids: Vec<String> = market_pairs
        .iter()
        .flat_map(|m| vec![m.yes_token.clone(), m.no_token.clone()])
        .collect();

    info!(
        "Subscribing to {} tokens ({} markets) via WebSocket...",
        token_ids.len(),
        market_pairs.len()
    );

    let mut arb_scanner = ArbScanner::new(config.min_arb_spread_pct);
    let mut arb_executor = ArbExecutor::new(config.clone());

    let (tx, mut rx) = mpsc::channel::<ws::BookEvent>(10_000);

    tokio::spawn(ws::connect_and_stream(
        config.ws_url.clone(),
        token_ids,
        tx,
    ));

    let mut updates_processed: u64 = 0;
    let mut arbs_found: u64 = 0;
    let start = std::time::Instant::now();

    info!("Listening for real-time order book updates...");

    while let Some(event) = rx.recv().await {
        match event {
            ws::BookEvent::Snapshot(book) => {
                arb_scanner.update_book(book);
            }
            ws::BookEvent::Update { token_id, bids, asks } => {
                if let Some(book) = arb_scanner.get_book(&token_id).cloned() {
                    let mut updated = book;
                    for level in &bids {
                        let price: f64 = level.price.parse().unwrap_or(0.0);
                        let size: f64 = level.size.parse().unwrap_or(0.0);
                        let key = types::to_price_key(price);
                        if size > 0.0 {
                            updated.bids.insert(key, size);
                        } else {
                            updated.bids.remove(&key);
                        }
                    }
                    for level in &asks {
                        let price: f64 = level.price.parse().unwrap_or(0.0);
                        let size: f64 = level.size.parse().unwrap_or(0.0);
                        let key = types::to_price_key(price);
                        if size > 0.0 {
                            updated.asks.insert(key, size);
                        } else {
                            updated.asks.remove(&key);
                        }
                    }
                    arb_scanner.update_book(updated);
                }
            }
        }

        updates_processed += 1;

        if updates_processed % 100 == 0 {
            let opportunities = arb_scanner.scan(&market_pairs);

            if !opportunities.is_empty() {
                arbs_found += opportunities.len() as u64;
                for opp in &opportunities {
                    arb_executor.execute(opp);
                }
            }

            if updates_processed % 5000 == 0 {
                let elapsed = start.elapsed().as_secs_f64();
                info!(
                    "Stats: {} updates | {:.0}/sec | {} arbs found | bankroll=${:.2}",
                    updates_processed,
                    updates_processed as f64 / elapsed,
                    arbs_found,
                    arb_executor.effective_bankroll()
                );
            }
        }
    }
}
