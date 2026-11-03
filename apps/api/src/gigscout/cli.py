"""Command-line interface: `gigscout --help`."""

import logging
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from gigscout.config import get_settings
from gigscout.profile_loader import ProfileError, load_profile
from gigscout.service import Mode, ScoutService

app = typer.Typer(
    help="GigScout — an AI lead scout that finds and qualifies client projects for software agencies.",
    no_args_is_help=True,
)
console = Console()
DEFAULT_PROFILE = Path("profiles/example.yaml")


def _service() -> ScoutService:
    return ScoutService.from_settings(get_settings())


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


@app.command()
def scout(
    profile: Path = typer.Option(DEFAULT_PROFILE, "--profile", "-p", help="YAML agency profile"),
    mode: Mode = typer.Option("auto", "--mode", "-m", help="team = multi-agent ReAct, pipeline = fixed graph"),
    show_trace: bool = typer.Option(False, "--trace", help="Print who-did-what in team mode"),
) -> None:
    """Run the agent once: search every source, qualify leads, and print a sales briefing."""
    try:
        user = load_profile(profile)
    except ProfileError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    with console.status("Scouting…"):
        result = _service().scout(user, mode)
    console.print(Markdown(result.report))
    if show_trace:
        for step in result.trace:
            console.print(f"[cyan]›[/cyan] {step}")
    console.print(f"\n[dim]mode={result.mode} queries={list(result.queries)} fetched={result.fetched_count} "
                  f"new={result.new_count} iterations={result.iterations}[/dim]")
    for error in result.errors:
        console.print(f"[yellow]warning:[/yellow] {error}")


@app.command()
def watch(
    profile: Path = typer.Option(DEFAULT_PROFILE, "--profile", "-p"),
    every: int = typer.Option(60, help="Minutes between runs", min=5),
    mode: Mode = typer.Option("auto", "--mode", "-m"),
) -> None:
    """Run the agent on a schedule until interrupted (Ctrl+C)."""
    while True:
        scout(profile, mode, show_trace=False)
        console.print(f"[dim]Next run in {every} min…[/dim]")
        time.sleep(every * 60)


@app.command()
def search(query: str, k: int = typer.Option(10, min=1, max=100)) -> None:
    """Semantic search over every lead collected so far."""
    table = Table("Similarity", "Title", "Kind", "Source", "URL")
    for c in _service().search(query, k):
        table.add_row(f"{c.similarity:.2f}", c.lead.title, c.lead.kind, c.lead.source, c.lead.url)
    console.print(table)


@app.command()
def ask(question: str, k: int = typer.Option(8, min=1, max=30)) -> None:
    """Ask a question answered from collected leads (RAG)."""
    answer = _service().ask(question, k)
    console.print(Markdown(answer.text))
    for i, c in enumerate(answer.sources, 1):
        console.print(f"[dim][{i}] {c.lead.title} — {c.lead.url}[/dim]")


@app.command()
def sources() -> None:
    """List enabled lead sources (pull) and inbound channels (push)."""
    for name in _service().source_names():
        console.print(f"• {name}")


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = typer.Option(False, "--reload", help="Restart on code changes (development)"),
) -> None:
    """Start the API for the web app (docs at /docs; Google Ads webhook at /webhooks/google-ads)."""
    import uvicorn

    uvicorn.run("gigscout.api:app", host=host, port=port, reload=reload, reload_dirs=["src"] if reload else None)


@app.command("create-admin")
def create_admin(
    email: str = typer.Option(..., "--email", "-e", help="Sign-in email"),
    name: str = typer.Option("Admin", "--name", "-n"),
    password: str = typer.Option(..., prompt=True, hide_input=True, confirmation_prompt=True),
) -> None:
    """Create an admin user for the web app (or reset an existing user's password and make them admin)."""
    from sqlalchemy import select

    from gigscout.platform.db import create_db
    from gigscout.platform.security import WeakPasswordError, hash_password
    from gigscout.platform.tables import User

    try:
        password_hash = hash_password(password)
    except WeakPasswordError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    engine, sessions = create_db(get_settings().resolved_database_url)
    with sessions() as session:
        user = session.scalar(select(User).where(User.email == email.lower()))
        if user is None:
            session.add(User(email=email.lower(), name=name, role="admin", password_hash=password_hash))
            verb = "Created"
        else:
            user.role, user.password_hash, user.is_active = "admin", password_hash, True
            verb = "Updated"
        session.commit()
    engine.dispose()
    console.print(f"[green]{verb} admin {email.lower()}[/green]")


if __name__ == "__main__":
    app()
