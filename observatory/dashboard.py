from datetime import datetime

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from shared.models import SaleResult

_console = Console()


def _status_label(roi: float) -> Text:
    if roi > 0.1:
        return Text("GOOD", style="bold green")
    if roi >= 0:
        return Text("FLAT", style="bold yellow")
    return Text("BAD", style="bold red")


def _profit_style(value: float) -> str:
    if value > 0:
        return "bold green"
    if value == 0:
        return "dim"
    return "bold red"


class Dashboard:
    def __init__(self, console: Console | None = None) -> None:
        self._console = console or _console

    def update(self, farms: list, cycle: int) -> None:
        """Render a Rich table snapshot for *farms* at *cycle*."""
        table = Table(
            title=f"[bold cyan]Multi-Farm System[/bold cyan]  ::  Cycle [bold]{cycle}[/bold]  "
                  f"[dim]{datetime.utcnow().strftime('%H:%M:%S')} UTC[/dim]",
            box=box.ROUNDED,
            show_lines=False,
            expand=False,
        )

        table.add_column("Farm", style="bold white", no_wrap=True)
        table.add_column("Capital", justify="right", style="cyan")
        table.add_column("Profit", justify="right")
        table.add_column("ROI", justify="right")
        table.add_column("Agents", justify="right", style="magenta")
        table.add_column("Status", justify="center")

        for farm in farms:
            style = _profit_style(farm.profit)
            roi_style = _profit_style(farm.roi)

            table.add_row(
                farm.name,
                f"${farm.capital:,.0f}",
                Text(f"${farm.profit:,.2f}", style=style),
                Text(f"{farm.roi:.4f}", style=roi_style),
                str(len(farm.producer_agents)),
                _status_label(farm.roi),
            )

        self._console.print(table)

    def log_sale(self, sale: SaleResult | dict, farm_name: str = "") -> None:
        """Print a single sale event in real time."""
        if isinstance(sale, dict):
            sold = sale.get("sold", False)
            amount = sale.get("price", sale.get("usd_amount", 0.0))
            item = sale.get("item", "dataset")
            tweet_url = sale.get("tweet_url")
            tweet_sim = sale.get("tweet_simulation", True)
        else:
            sold = sale.sold
            amount = sale.usd_amount
            item = sale.item
            tweet_url = None
            tweet_sim = True

        farm_tag = f"[dim]{farm_name}[/dim] " if farm_name else ""

        # Traffic-farm entries: show tweet result instead of a generic sale line
        if isinstance(sale, dict) and tweet_url is not None:
            sim_tag = " [dim](sim)[/dim]" if tweet_sim else ""
            self._console.print(
                f"{farm_tag}[bold cyan]TWEET[/bold cyan]{sim_tag}  "
                f"[white]{item}[/white]  "
                f"[blue]{tweet_url}[/blue]"
            )
            return

        if sold:
            self._console.print(
                f"{farm_tag}[bold green]SOLD[/bold green]  "
                f"[white]{item}[/white]  [bold yellow]${amount:.2f}[/bold yellow]"
            )
        else:
            self._console.print(
                f"{farm_tag}[bold red]EXPIRED[/bold red]  [dim]{item}[/dim]"
            )
