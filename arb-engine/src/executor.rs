use crate::config::Config;
use crate::types::ArbOpportunity;
use tracing::{info, warn};

pub struct ArbExecutor {
    config: Config,
    total_exposure: f64,
    realized_pnl: f64,
}

impl ArbExecutor {
    pub fn new(config: Config) -> Self {
        Self {
            config,
            total_exposure: 0.0,
            realized_pnl: 0.0,
        }
    }

    pub fn effective_bankroll(&self) -> f64 {
        (self.config.bankroll_usdc + self.realized_pnl).max(0.01)
    }

    pub fn can_trade(&self, cost: f64) -> bool {
        if cost > self.config.max_position_usdc {
            return false;
        }
        if self.total_exposure + cost > self.config.max_exposure_usdc {
            return false;
        }
        true
    }

    pub fn execute(&mut self, opp: &ArbOpportunity) {
        let max_spend = self.config.max_position_usdc
            .min(self.config.max_exposure_usdc - self.total_exposure);

        if max_spend <= 0.0 {
            warn!("No budget left, skipping arb on {}", opp.market.slug);
            return;
        }

        let shares = max_spend / opp.total_cost;
        let cost = opp.total_cost * shares;
        let profit = opp.profit_per_share * shares;

        if !self.can_trade(cost) {
            warn!("Risk check failed for ${:.2} on {}", cost, opp.market.slug);
            return;
        }

        if self.config.dry_run {
            info!(
                "[DRY RUN] ARB: {:.1} shares @ ${:.4} (${:.2}) profit=${:.4} spread={:.2}% on {}",
                shares, opp.total_cost, cost, profit, opp.spread_pct, opp.market.slug
            );
            return;
        }

        info!(
            "EXECUTING ARB: {:.1} shares @ ${:.4} profit=${:.4} on {}",
            shares, opp.total_cost, profit, opp.market.slug
        );

        // TODO: Place FOK orders via CLOB API for both YES and NO tokens
        // For now, log the intent. Real execution requires EIP-712 signing
        // which needs the full rs-clob-client or custom signing implementation.

        self.total_exposure += cost;
    }

    pub fn record_profit(&mut self, pnl: f64) {
        self.realized_pnl += pnl;
        info!(
            "P&L update: ${:+.4} | bankroll=${:.2} | exposure=${:.2}",
            pnl, self.effective_bankroll(), self.total_exposure
        );
    }
}
