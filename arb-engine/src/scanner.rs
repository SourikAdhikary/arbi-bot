use crate::types::{ArbOpportunity, MarketPair, OrderBook};
use std::collections::HashMap;
use tracing::info;

pub struct ArbScanner {
    min_spread_pct: f64,
    books: HashMap<String, OrderBook>,
}

impl ArbScanner {
    pub fn new(min_spread_pct: f64) -> Self {
        Self {
            min_spread_pct,
            books: HashMap::new(),
        }
    }

    pub fn update_book(&mut self, book: OrderBook) {
        self.books.insert(book.token_id.clone(), book);
    }

    pub fn get_book(&self, token_id: &str) -> Option<&OrderBook> {
        self.books.get(token_id)
    }

    pub fn scan(&self, markets: &[MarketPair]) -> Vec<ArbOpportunity> {
        let mut opportunities = Vec::new();

        for market in markets {
            if let Some(opp) = self.check_market(market) {
                opportunities.push(opp);
            }
        }

        opportunities.sort_by(|a, b| b.spread_pct.partial_cmp(&a.spread_pct).unwrap());
        opportunities
    }

    fn check_market(&self, market: &MarketPair) -> Option<ArbOpportunity> {
        let yes_book = self.books.get(&market.yes_token)?;
        let no_book = self.books.get(&market.no_token)?;

        let yes_ask = yes_book.best_ask()?;
        let no_ask = no_book.best_ask()?;

        let total_cost = yes_ask + no_ask;
        if total_cost >= 1.0 {
            return None;
        }

        let spread_pct = (1.0 - total_cost) * 100.0;
        if spread_pct < self.min_spread_pct {
            return None;
        }

        let profit_per_share = 1.0 - total_cost;

        info!(
            "ARB FOUND: {:.2}% spread | cost={:.4} | profit={:.4}/sh | {}",
            spread_pct, total_cost, profit_per_share, &market.question[..market.question.len().min(50)]
        );

        Some(ArbOpportunity {
            market: market.clone(),
            yes_ask,
            no_ask,
            total_cost,
            spread_pct,
            profit_per_share,
        })
    }
}
