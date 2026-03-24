use serde::Deserialize;
use std::collections::BTreeMap;

#[derive(Debug, Clone)]
pub struct OrderBook {
    pub token_id: String,
    pub bids: BTreeMap<u64, f64>,
    pub asks: BTreeMap<u64, f64>,
}

impl OrderBook {
    pub fn new(token_id: String) -> Self {
        Self {
            token_id,
            bids: BTreeMap::new(),
            asks: BTreeMap::new(),
        }
    }

    pub fn best_bid(&self) -> Option<f64> {
        self.bids.keys().next_back().map(|&k| from_price_key(k))
    }

    pub fn best_ask(&self) -> Option<f64> {
        self.asks.keys().next().map(|&k| from_price_key(k))
    }

    pub fn spread(&self) -> Option<f64> {
        match (self.best_bid(), self.best_ask()) {
            (Some(bid), Some(ask)) => Some(ask - bid),
            _ => None,
        }
    }
}

pub fn to_price_key(price: f64) -> u64 {
    (price * 1_000_000.0) as u64
}

pub fn from_price_key(key: u64) -> f64 {
    key as f64 / 1_000_000.0
}

#[derive(Debug, Clone)]
pub struct MarketPair {
    pub condition_id: String,
    pub question: String,
    pub slug: String,
    pub yes_token: String,
    pub no_token: String,
    pub neg_risk: bool,
    pub volume: f64,
}

#[derive(Debug, Clone)]
pub struct ArbOpportunity {
    pub market: MarketPair,
    pub yes_ask: f64,
    pub no_ask: f64,
    pub total_cost: f64,
    pub spread_pct: f64,
    pub profit_per_share: f64,
}

#[derive(Debug, Deserialize)]
pub struct WsMessage {
    #[serde(default)]
    pub event_type: String,
    #[serde(default)]
    pub asset_id: String,
    #[serde(default)]
    pub market: String,
    #[serde(default)]
    pub price: Option<String>,
    #[serde(default)]
    pub side: Option<String>,
    #[serde(default)]
    pub size: Option<String>,
    #[serde(default)]
    pub bids: Option<Vec<PriceLevel>>,
    #[serde(default)]
    pub asks: Option<Vec<PriceLevel>>,
}

#[derive(Debug, Deserialize, Clone)]
pub struct PriceLevel {
    pub price: String,
    pub size: String,
}

/// Raw Gamma API market — all fields are strings or JSON-encoded strings.
#[derive(Debug, Deserialize)]
pub struct GammaMarket {
    #[serde(rename = "conditionId", default)]
    pub condition_id: String,
    #[serde(default)]
    pub question: String,
    #[serde(default)]
    pub slug: String,
    #[serde(rename = "clobTokenIds", default)]
    pub clob_token_ids: serde_json::Value,
    #[serde(default)]
    pub outcomes: serde_json::Value,
    #[serde(default)]
    pub active: bool,
    #[serde(default)]
    pub closed: bool,
    #[serde(rename = "negRisk", default)]
    pub neg_risk: bool,
    #[serde(default)]
    pub volume: serde_json::Value,
}

impl GammaMarket {
    pub fn volume_f64(&self) -> f64 {
        match &self.volume {
            serde_json::Value::Number(n) => n.as_f64().unwrap_or(0.0),
            serde_json::Value::String(s) => s.parse().unwrap_or(0.0),
            _ => 0.0,
        }
    }

    pub fn token_ids(&self) -> Vec<String> {
        match &self.clob_token_ids {
            serde_json::Value::Array(arr) => {
                arr.iter().filter_map(|v| v.as_str().map(String::from)).collect()
            }
            serde_json::Value::String(s) => {
                serde_json::from_str(s).unwrap_or_default()
            }
            _ => Vec::new(),
        }
    }
}
