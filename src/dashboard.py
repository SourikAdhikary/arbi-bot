"""Live terminal dashboard using Rich — 3-strategy view with compounding stats."""

from __future__ import annotations

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.config import trading_cfg
from src.executor import ExecutionResult
from src.risk import RiskManager
from src.strategies.correlation import CorrelationOpportunity
from src.strategies.endgame import EndgameOpportunity
from src.strategies.value import ValueOpportunity


class Dashboard:
    def __init__(self, risk: RiskManager) -> None:
        self._risk = risk
        self._dry_run = trading_cfg.dry_run
        self._console = Console()
        self._endgame_opps: list[EndgameOpportunity] = []
        self._value_opps: list[ValueOpportunity] = []
        self._corr_opps: list[CorrelationOpportunity] = []
        self._recent_executions: list[ExecutionResult] = []
        self._scan_count: int = 0
        self._markets_count: int = 0
        self._live: Live | None = None

    def start(self) -> Live:
        self._live = Live(
            self._build_layout(),
            console=self._console,
            refresh_per_second=2,
            screen=True,
        )
        return self._live

    def update(
        self,
        endgame_opps: list[EndgameOpportunity] | None = None,
        value_opps: list[ValueOpportunity] | None = None,
        corr_opps: list[CorrelationOpportunity] | None = None,
        executions: list[ExecutionResult] | None = None,
        scan_count: int | None = None,
        markets_count: int | None = None,
    ) -> None:
        if endgame_opps is not None:
            self._endgame_opps = endgame_opps
        if value_opps is not None:
            self._value_opps = value_opps
        if corr_opps is not None:
            self._corr_opps = corr_opps
        if executions is not None:
            self._recent_executions = (executions + self._recent_executions)[:50]
        if scan_count is not None:
            self._scan_count = scan_count
        if markets_count is not None:
            self._markets_count = markets_count

        if self._live is not None:
            self._live.update(self._build_layout())

    def _build_layout(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(self._header_panel(), size=6),
            Layout(name="strategies"),
            Layout(self._execution_panel(), size=12),
        )
        layout["strategies"].split_row(
            Layout(self._endgame_panel()),
            Layout(self._value_panel()),
            Layout(self._corr_panel()),
        )
        return layout

    def _header_panel(self) -> Panel:
        r = self._risk
        mode = "[bold yellow]DRY RUN[/]" if self._dry_run else "[bold red]LIVE[/]"
        growth = ((r.effective_bankroll / trading_cfg.bankroll_usdc) - 1) * 100

        lines = [
            f"Mode: {mode}  |  Scans: {self._scan_count}  |  Markets: {self._markets_count}",
            (
                f"Bankroll: [bold]${r.effective_bankroll:.2f}[/]  "
                f"(started ${trading_cfg.bankroll_usdc:.2f}, "
                f"{'[green]+' if growth >= 0 else '[red]'}{growth:.1f}%[/])  |  "
                f"P&L: ${r.realized_pnl:+.2f}  |  "
                f"Exposure: ${r.total_exposure:.2f}/${r.max_total_exposure_usdc:.2f}"
            ),
            (
                f"Positions: {r.position_count}  |  "
                f"W/L: {r.win_count}/{r.loss_count} ({r.win_rate:.0f}%)  |  "
                f"Max Bet: ${r.max_position_usdc:.2f}"
            ),
        ]
        if r.is_killed:
            lines.append("[bold red]*** KILL SWITCH ACTIVE ***[/]")

        text = Text.from_markup("\n".join(lines))
        return Panel(text, title="[bold cyan]Polymarket Sniper v2 (Auto-Compound)[/]", border_style="cyan")

    def _endgame_panel(self) -> Panel:
        table = Table(show_header=True, header_style="bold green", expand=True, padding=(0, 1))
        table.add_column("Sc", width=4)
        table.add_column("$", width=5)
        table.add_column("+$", width=4)
        table.add_column("D", width=3)
        table.add_column("Market", ratio=1)

        for i, o in enumerate(self._endgame_opps[:8]):
            s = "bold" if i == 0 else ""
            table.add_row(f"{o.score:.0f}", f"{o.price:.2f}", f"{o.profit_per_share:.2f}",
                          f"{o.days_to_end:.0f}", o.market_question[:30], style=s)

        return Panel(table, title=f"[green]Endgame ({len(self._endgame_opps)})[/]", border_style="green")

    def _value_panel(self) -> Panel:
        table = Table(show_header=True, header_style="bold yellow", expand=True, padding=(0, 1))
        table.add_column("Sc", width=4)
        table.add_column("Edge", width=5)
        table.add_column("Sig", width=6)
        table.add_column("Market", ratio=1)

        for i, o in enumerate(self._value_opps[:8]):
            s = "bold" if i == 0 else ""
            table.add_row(f"{o.score:.0f}", f"{o.edge_pct:+.0f}%", o.signal[:6],
                          o.market_question[:30], style=s)

        return Panel(table, title=f"[yellow]Value ({len(self._value_opps)})[/]", border_style="yellow")

    def _corr_panel(self) -> Panel:
        table = Table(show_header=True, header_style="bold blue", expand=True, padding=(0, 1))
        table.add_column("Sc", width=4)
        table.add_column("Lag", width=5)
        table.add_column("Grp", width=8)
        table.add_column("Market", ratio=1)

        for i, o in enumerate(self._corr_opps[:8]):
            s = "bold" if i == 0 else ""
            table.add_row(f"{o.score:.0f}", f"{o.lag_pct:+.0f}%", o.group[:8],
                          o.market_question[:30], style=s)

        return Panel(table, title=f"[blue]Correlation ({len(self._corr_opps)})[/]", border_style="blue")

    def _execution_panel(self) -> Panel:
        table = Table(show_header=True, header_style="bold magenta", expand=True)
        table.add_column("Strat", width=8)
        table.add_column("Status", width=6)
        table.add_column("Cost", width=8)
        table.add_column("Profit", width=8)
        table.add_column("Message", ratio=1)

        for ex in self._recent_executions[:8]:
            status = "[green]OK[/]" if ex.success else "[red]SKIP[/]"
            table.add_row(
                ex.opportunity_type[:8],
                status,
                f"${ex.total_cost:.2f}",
                f"${ex.expected_profit:.2f}",
                ex.message[:55],
            )

        return Panel(table, title="[bold magenta]Executions[/]", border_style="magenta")
