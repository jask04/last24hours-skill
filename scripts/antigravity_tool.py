import subprocess
from pathlib import Path

def forecast_last_24_hours(topic: str, quick: bool = True, emit: str = "compact") -> str:
    """Forecasts a topic or discovers market picks from the last 24 hours using prediction markets, sports, weather, and web sources.
    
    Args:
        topic: The topic to forecast or query (e.g., 'NBA games tomorrow', 'Fed rate cut', 'markets to watch').
        quick: If True, performs a faster research pass with fewer sources. Defaults to True.
        emit: Output mode for the results. Can be 'compact', 'json', 'md', 'context', or 'path'. Defaults to 'compact'.
        
    Returns:
        A markdown-formatted string containing the forecast report or market watchlist.
    """
    script_path = Path(__file__).parent / "last24hours.py"
    
    cmd = ["python3", str(script_path), topic]
    
    if quick:
        cmd.append("--quick")
    
    if emit:
        cmd.append(f"--emit={emit}")
        
    try:
        # We run the command and capture stdout/stderr. 
        # last24hours.py might output progress info to stderr, which we can ignore or return on error.
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        error_msg = f"Error running last24hours forecast (exit code {e.returncode}):\n{e.stderr}"
        if e.stdout:
            error_msg += f"\nPartial output:\n{e.stdout}"
        return error_msg
