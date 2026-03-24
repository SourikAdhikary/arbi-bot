use std::env;

#[derive(Debug, Clone)]
pub struct Config {
    pub ws_url: String,
    pub clob_url: String,
    pub gamma_url: String,
    pub private_key: String,

    pub min_arb_spread_pct: f64,
    pub max_position_usdc: f64,
    pub max_exposure_usdc: f64,
    pub bankroll_usdc: f64,
    pub dry_run: bool,
}

impl Config {
    pub fn from_env() -> Self {
        Self {
            ws_url: env("ARB_WS_URL", "wss://ws-subscriptions-clob.polymarket.com/ws/market"),
            clob_url: env("ARB_CLOB_URL", "https://clob.polymarket.com"),
            gamma_url: env("ARB_GAMMA_URL", "https://gamma-api.polymarket.com"),
            private_key: env("POLYMARKET_PRIVATE_KEY", ""),
            min_arb_spread_pct: env("ARB_MIN_SPREAD_PCT", "0.5").parse().unwrap_or(0.5),
            max_position_usdc: env("ARB_MAX_POSITION_USDC", "2.0").parse().unwrap_or(2.0),
            max_exposure_usdc: env("ARB_MAX_EXPOSURE_USDC", "8.0").parse().unwrap_or(8.0),
            bankroll_usdc: env("BANKROLL_USDC", "10.0").parse().unwrap_or(10.0),
            dry_run: env("DRY_RUN", "true") == "true",
        }
    }
}

fn env(key: &str, default: &str) -> String {
    env::var(key).unwrap_or_else(|_| default.to_string())
}
