use crate::types::{GammaMarket, MarketPair};
use tracing::{debug, error, info, warn};

pub async fn fetch_binary_markets(gamma_url: &str, limit: usize) -> Vec<MarketPair> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .build()
        .unwrap();
    let mut markets = Vec::new();
    let mut offset = 0;
    let mut total_raw = 0usize;
    let mut skipped_no_tokens = 0usize;
    let mut skipped_not_binary = 0usize;

    while markets.len() < limit {
        let url = format!(
            "{}/markets?active=true&closed=false&limit=100&offset={}&order=volume&ascending=false",
            gamma_url, offset
        );
        debug!("Fetching: {}", url);

        let resp = match client.get(&url).send().await {
            Ok(r) => r,
            Err(e) => {
                error!("HTTP request failed: {}", e);
                break;
            }
        };

        let status = resp.status();
        let body = match resp.text().await {
            Ok(b) => b,
            Err(e) => {
                error!("Failed to read response body: {}", e);
                break;
            }
        };

        if !status.is_success() {
            error!("Gamma API returned {}: {}", status, &body[..body.len().min(300)]);
            break;
        }

        let batch: Vec<GammaMarket> = match serde_json::from_str(&body) {
            Ok(b) => b,
            Err(e) => {
                error!("JSON parse error: {}", e);
                warn!("Response preview: {}", &body[..body.len().min(500)]);
                break;
            }
        };

        if batch.is_empty() {
            break;
        }

        total_raw += batch.len();

        if offset == 0 && !batch.is_empty() {
            let sample = &batch[0];
            info!(
                "Sample market: question={:?}, clobTokenIds={}, volume={}",
                &sample.question[..sample.question.len().min(60)],
                sample.clob_token_ids,
                sample.volume
            );
        }

        for raw in &batch {
            match parse_binary_market(raw) {
                Some(pair) => markets.push(pair),
                None => {
                    let ids = raw.token_ids();
                    if ids.is_empty() {
                        skipped_no_tokens += 1;
                    } else {
                        skipped_not_binary += 1;
                    }
                }
            }
        }

        info!(
            "Page offset={}: {} raw -> {} binary total (skipped: {} no-tokens, {} non-binary)",
            offset, batch.len(), markets.len(), skipped_no_tokens, skipped_not_binary
        );

        offset += 100;
    }

    info!(
        "Done: {} binary markets from {} raw (skipped {} no-tokens, {} non-binary)",
        markets.len(), total_raw, skipped_no_tokens, skipped_not_binary
    );
    markets
}

fn parse_binary_market(raw: &GammaMarket) -> Option<MarketPair> {
    let ids = raw.token_ids();

    if ids.len() != 2 {
        return None;
    }

    if ids[0].is_empty() || ids[1].is_empty() {
        return None;
    }

    Some(MarketPair {
        condition_id: raw.condition_id.clone(),
        question: raw.question.clone(),
        slug: raw.slug.clone(),
        yes_token: ids[0].clone(),
        no_token: ids[1].clone(),
        neg_risk: raw.neg_risk,
        volume: raw.volume_f64(),
    })
}
