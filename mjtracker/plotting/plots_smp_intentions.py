"""
SMP Intentions plotting module.

This module provides clean, maintainable functions for plotting aggregated 
intention data for the 2027 presidential election. It handles gap detection,
segment splitting, error bands, and annotations.

Based on sandbox/plot_intentions_2027.py but refactored following clean code principles.
"""

from typing import Optional, List, Tuple
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from ..plotting.plot_utils import load_colors
from ..core.smp_data import SMPData


# Constants for visual styling
DEFAULT_MAX_GAP_DAYS = 60
DEFAULT_CONNECT_GAP_DAYS = 150
DEFAULT_MARKER_SIZE = 6
DEFAULT_RAW_MARKER_SIZE = 5
DEFAULT_LINE_WIDTH = 1
DEFAULT_GREYED_LINE_WIDTH = 0.3
DEFAULT_ERROR_BAND_OPACITY = 0.2
DEFAULT_RAW_MARKER_OPACITY = 0.6
DEFAULT_GREYED_OPACITY = 0.3




def rank2str(rank: int) -> str:
    """
    Convert rank number to ordinal string.
    
    Parameters
    ----------
    rank : int
        Numerical rank (1, 2, 3, ...)
    
    Returns
    -------
    str
        Ordinal string ('1er', '2ème', '3ème', ...)
    
    Examples
    --------
    >>> rank2str(1)
    '1er'
    >>> rank2str(2)
    '2ème'
    """
    if rank == 1:
        return "1er"
    if rank == 2:
        return "2ème"
    if rank == 3:
        return "3ème"
    return f"{int(rank)}ème"


def _extended_name_annotations(
    df: pd.DataFrame,
    candidate: Optional[str] = None,
    show_rank: bool = True,
    show_intention: bool = True,
    breaks_in_names: bool = True,
) -> str:
    """
    Build formatted annotation text for a candidate.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing candidate data
    candidate : Optional[str]
        Candidate name
    show_rank : bool, default=True
        Include rank in annotation
    show_intention : bool, default=True
        Include intention percentage in annotation
    breaks_in_names : bool, default=True
        Add line breaks in names (currently disabled)
    
    Returns
    -------
    str
        Formatted annotation text
    """
    text = candidate if candidate else ""
    annotations = []

    if show_rank and "rang" in df.columns:
        rank = df["rang"].iloc[-1]
        annotations.append(rank2str(rank))

    if show_intention and "valeur" in df.columns:
        intention = df["valeur"].iloc[-1]
        annotations.append(f"{intention:.1f}%")

    if annotations:
        text += " (" + ", ".join(annotations) + ")"

    return text


def _get_candidate_color(candidate: str, colored: bool) -> str:
    """Get color for a candidate based on highlighting status."""
    if not colored:
        return "#d3d3d3"
    
    colors = load_colors()
    return colors.get(candidate, {}).get("couleur", "#d3d3d3")


def _prepare_aggregation_dict(df: pd.DataFrame, col_intention: str) -> dict:
    """Build aggregation dictionary for groupby operation."""
    agg_dict = {
        col_intention: "mean",
        "candidat": "first",
    }
    
    optional_columns = {
        "rang": "first",
        "erreur_sup": "mean",
        "erreur_inf": "mean",
    }
    
    for col, agg_func in optional_columns.items():
        if col in df.columns:
            agg_dict[col] = agg_func
    
    return agg_dict


def _aggregate_polls_by_date(df: pd.DataFrame, col_intention: str) -> pd.DataFrame:
    """
    Group polls by date and calculate mean when multiple polls on same day.
    
    This prevents visual clutter and provides a cleaner representation
    when multiple polling institutes publish on the same date.
    """
    df_copy = df.copy()
    df_copy["fin_enquete"] = pd.to_datetime(df_copy["fin_enquete"])
    df_copy = df_copy.sort_values("fin_enquete")
    
    agg_dict = _prepare_aggregation_dict(df_copy, col_intention)
    return df_copy.groupby("fin_enquete").agg(agg_dict).reset_index()


def _detect_time_segments(df: pd.DataFrame, max_gap_days: int) -> List[pd.DataFrame]:
    """
    Split data into continuous time segments based on gap detection.
    
    This is a critical feature to avoid misleading visualizations where
    curves connect data points separated by long periods with no polling.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with 'fin_enquete' datetime column, must be sorted
    max_gap_days : int
        Maximum gap in days before starting a new segment
    
    Returns
    -------
    List[pd.DataFrame]
        List of continuous time segments
    """
    segments = []
    current_segment = []
    
    for idx, row_data in df.iterrows():
        if not current_segment:
            current_segment.append(row_data)
        else:
            time_gap = (row_data["fin_enquete"] - current_segment[-1]["fin_enquete"]).days
            
            if time_gap <= max_gap_days:
                current_segment.append(row_data)
            else:
                if current_segment:
                    segments.append(pd.DataFrame(current_segment))
                current_segment = [row_data]
    
    if current_segment:
        segments.append(pd.DataFrame(current_segment))
    
    return segments


def _should_connect_segments(segments: List[pd.DataFrame], segment_idx: int, connect_gap_days: int) -> bool:
    """Check if current segment should be connected to next with dotted line."""
    if segment_idx >= len(segments) - 1:
        return False
    
    current_segment = segments[segment_idx]
    next_segment = segments[segment_idx + 1]
    
    time_gap = (
        next_segment["fin_enquete"].iloc[0] -
        current_segment["fin_enquete"].iloc[-1]
    ).days
    
    return time_gap <= connect_gap_days


def _add_segment_trace(
    fig: go.Figure,
    segment_df: pd.DataFrame,
    candidate: str,
    col_intention: str,
    color: str,
    width: float,
    colored: bool,
    row: Optional[int],
    col: Optional[int],
) -> None:
    """Add main trace for a time segment."""
    mode = "lines"
    
    fig.add_trace(
        go.Scatter(
            x=segment_df["fin_enquete"],
            y=segment_df[col_intention],
            mode=mode,
            line=dict(color=color, width=width) if colored else None,
            marker=dict(color=color, size=DEFAULT_MARKER_SIZE, opacity=0.8),
            name=candidate,
            showlegend=False,
            legendgroup=None,
        ),
        row=row,
        col=col,
    )


def _add_dotted_connection(
    fig: go.Figure,
    current_segment: pd.DataFrame,
    next_segment: pd.DataFrame,
    col_intention: str,
    color: str,
    width: float,
    row: Optional[int],
    col: Optional[int],
) -> None:
    """Add dotted line connecting two segments across a gap."""
    fig.add_trace(
        go.Scatter(
            x=[current_segment["fin_enquete"].iloc[-1], next_segment["fin_enquete"].iloc[0]],
            y=[current_segment[col_intention].iloc[-1], next_segment[col_intention].iloc[0]],
            mode="lines",
            line=dict(color=color, width=width, dash="dot"),
            hoverinfo="skip",
            showlegend=False,
            legendgroup=None,
        ),
        row=row,
        col=col,
    )


def _add_rank_marker(
    fig: go.Figure,
    segment_df: pd.DataFrame,
    candidate: str,
    col_intention: str,
    color: str,
    opacity: float,
    row: Optional[int],
    col: Optional[int],
) -> None:
    """Add final point marker with rank indicator."""
    if "rang" not in segment_df.columns:
        return
    
    rank = segment_df["rang"].iloc[-1]
    
    fig.add_trace(
        go.Scatter(
            x=segment_df["fin_enquete"].iloc[-1:],
            y=segment_df[col_intention].iloc[-1:],
            mode="markers",
            name=candidate,
            marker=dict(color=color, opacity=opacity, size=8),
            legendgroup=None,
            showlegend=False,
            text=[rank2str(rank)],
        ),
        row=row,
        col=col,
    )


def _add_error_bands(
    fig: go.Figure,
    segments: List[pd.DataFrame],
    color: str,
    row: Optional[int],
    col: Optional[int],
) -> None:
    """Add confidence interval bands for each segment."""
    rgb = px.colors.hex_to_rgb(color)
    fill_color = f"rgba({rgb[0]},{rgb[1]},{rgb[2]},{DEFAULT_ERROR_BAND_OPACITY})"
    
    for segment_df in segments:
        if len(segment_df) < 2:
            continue
        
        if "erreur_sup" not in segment_df.columns or "erreur_inf" not in segment_df.columns:
            continue
        
        x_dates = segment_df["fin_enquete"].tolist()
        y_upper = segment_df["erreur_sup"].tolist()
        y_lower = segment_df["erreur_inf"].tolist()
        
        fig.add_scatter(
            x=x_dates + x_dates[::-1],
            y=y_upper + y_lower[::-1],
            fill="toself",
            fillcolor=fill_color,
            line=dict(color="rgba(255,255,255,0)"),
            hoverinfo="skip",
            showlegend=False,
            legendgroup=None,
            row=row,
            col=col,
        )


def _add_candidate_annotation(
    fig: go.Figure,
    segment_df: pd.DataFrame,
    candidate: str,
    col_intention: str,
    color: str,
    show_rank: bool,
    row: Optional[int],
    col: Optional[int],
) -> None:
    """Add text annotation for candidate's final value."""
    annotation_text = _extended_name_annotations(
        segment_df,
        candidate=candidate,
        show_rank=show_rank,
        show_intention=True,
        breaks_in_names=True,
    )
    
    fig.add_annotation(
        x=pd.to_datetime(segment_df["fin_enquete"].iloc[-1]),
        y=segment_df[col_intention].iloc[-1],
        xanchor="left",
        xshift=10,
        yanchor="middle",
        text=f"<b>{annotation_text}</b>",
        font=dict(family="Arial", size=12, color=color),
        showarrow=False,
        row=row,
        col=col,
    )


def plot_intention(
    df: pd.DataFrame,
    col_intention: str,
    fig: Optional[go.Figure] = None,
    colored: bool = True,
    row: Optional[int] = None,
    col: Optional[int] = None,
    max_gap_days: int = DEFAULT_MAX_GAP_DAYS,
    connect_gap_days: int = DEFAULT_CONNECT_GAP_DAYS,
) -> go.Figure:
    """
    Plot aggregated intention curve for a single candidate with intelligent gap detection.
    
    This function handles time series data with potential gaps, splitting the curve
    into continuous segments and connecting them with dotted lines when appropriate.
    It also adds error bands and annotations.
    
    Key Features
    ------------
    - Automatic gap detection to avoid misleading visualizations
    - Segment splitting for discontinuous data
    - Error bands for confidence intervals
    - Dotted connections between segments
    - Smart annotations with rank and percentage
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing data for a single candidate
    col_intention : str
        Column name for intention values
    fig : Optional[go.Figure], default=None
        Existing figure to add to, or None to create new
    colored : bool, default=True
        Use candidate-specific colors (False for greyed out)
    row : Optional[int], default=None
        Subplot row number
    col : Optional[int], default=None
        Subplot column number
    max_gap_days : int, default=60
        Maximum gap in days to keep points in same segment
    connect_gap_days : int, default=150
        Maximum gap to connect segments with dotted line
    
    Returns
    -------
    go.Figure
        Updated Plotly figure
    """
    if fig is None:
        fig = go.Figure()
    
    candidate = df["candidat"].unique()[0]
    color = _get_candidate_color(candidate, colored)
    opacity = 1 if colored else DEFAULT_GREYED_OPACITY
    width = DEFAULT_LINE_WIDTH if colored else DEFAULT_GREYED_LINE_WIDTH
    
    df_aggregated = _aggregate_polls_by_date(df, col_intention)
    segments = _detect_time_segments(df_aggregated, max_gap_days)
    
    for i, segment_df in enumerate(segments):
        if len(segment_df) >= 2 or (i == len(segments) - 1 and not segment_df.empty):
            _add_segment_trace(fig, segment_df, candidate, col_intention, color, width, colored, row, col)
            
            if colored and _should_connect_segments(segments, i, connect_gap_days):
                _add_dotted_connection(fig, segment_df, segments[i + 1], col_intention, color, width, row, col)
    
    if colored:
        _add_error_bands(fig, segments, color, row, col)
        
        if segments:
            _add_rank_marker(fig, segments[-1], candidate, col_intention, color, opacity, row, col)
            _add_candidate_annotation(fig, segments[-1], candidate, col_intention, color, show_rank=False, row=row, col=col)
    
    return fig


def _add_raw_data_line(
    fig: go.Figure,
    segment_df: pd.DataFrame,
    candidate: str,
    col_intention: str,
    color: str,
    row: Optional[int],
    col: Optional[int],
) -> None:
    """Add thin dotted line connecting raw data points within segment."""
    fig.add_trace(
        go.Scatter(
            x=segment_df["fin_enquete"],
            y=segment_df[col_intention],
            mode="lines",
            line=dict(color=color, width=1, dash="dot"),
            hoverinfo="skip",
            name=candidate,
            showlegend=False,
            legendgroup=None,
        ),
        row=row,
        col=col,
    )


def _add_raw_data_markers(
    fig: go.Figure,
    segment_df: pd.DataFrame,
    candidate: str,
    col_intention: str,
    color: str,
    opacity: float,
    row: Optional[int],
    col: Optional[int],
) -> None:
    """Add scatter markers for raw poll data points."""
    # Build custom hover text with all available information
    hover_texts = []
    for _, row in segment_df.iterrows():
        text_parts = [f"<b>{candidate}</b>"]
        text_parts.append(f"Date: {pd.to_datetime(row['fin_enquete']).strftime('%Y-%m-%d')}")
        text_parts.append(f"Intention: {row[col_intention]:.1f}%")
        print(row.columns)
        if 'institut' in row and pd.notna(row['institut']):
            text_parts.append(f"Institut: {row['institut']}")
        
        if 'commanditaire' in row and pd.notna(row['commanditaire']):
            text_parts.append(f"Commanditaire: {row['commanditaire']}")
        
        hover_texts.append("<br>".join(text_parts))
    
    fig.add_trace(
        go.Scatter(
            x=segment_df["fin_enquete"],
            y=segment_df[col_intention],
            mode="markers",
            marker=dict(color=color, opacity=opacity, size=DEFAULT_RAW_MARKER_SIZE),
            # hovertext=hover_texts,
            hoverinfo="text",
            name=candidate,
            showlegend=False,
            legendgroup=None,
        ),
        row=row,
        col=col,
    )


def plot_raw_data_lines(
    df: pd.DataFrame,
    col_intention: str,
    fig: Optional[go.Figure] = None,
    colored: bool = True,
    row: Optional[int] = None,
    col: Optional[int] = None,
    max_gap_days: int = DEFAULT_MAX_GAP_DAYS,
) -> go.Figure:
    """
    Plot dotted lines connecting raw data points within segments.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with raw poll data for a single candidate
    col_intention : str
        Column name for intention values
    fig : Optional[go.Figure], default=None
        Existing figure to add to
    colored : bool, default=True
        Use candidate-specific colors
    row : Optional[int], default=None
        Subplot row number
    col : Optional[int], default=None
        Subplot column number
    max_gap_days : int, default=60
        Maximum gap for segment detection
    
    Returns
    -------
    go.Figure
        Updated figure
    """
    if fig is None:
        fig = go.Figure()

    candidate = df["candidat"].unique()[0]
    colors = load_colors()
    color = colors.get(candidate, {}).get("couleur", "lightgray") if colored else "lightgray"
    
    df_copy = df.copy()
    df_copy["fin_enquete"] = pd.to_datetime(df_copy["fin_enquete"])
    df_copy = df_copy.sort_values("fin_enquete")
    
    segments = _detect_time_segments(df_copy, max_gap_days)
    
    for segment_df in segments:
        if len(segment_df) >= 2 and colored:
            _add_raw_data_line(fig, segment_df, candidate, col_intention, color, row, col)

    return fig


def plot_raw_data_markers(
    df: pd.DataFrame,
    col_intention: str,
    fig: Optional[go.Figure] = None,
    colored: bool = True,
    row: Optional[int] = None,
    col: Optional[int] = None,
    max_gap_days: int = DEFAULT_MAX_GAP_DAYS,
) -> go.Figure:
    """
    Plot scatter markers for raw poll data points.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with raw poll data for a single candidate
    col_intention : str
        Column name for intention values
    fig : Optional[go.Figure], default=None
        Existing figure to add to
    colored : bool, default=True
        Use candidate-specific colors
    row : Optional[int], default=None
        Subplot row number
    col : Optional[int], default=None
        Subplot column number
    max_gap_days : int, default=60
        Maximum gap for segment detection
    
    Returns
    -------
    go.Figure
        Updated figure
    """
    if fig is None:
        fig = go.Figure()

    candidate = df["candidat"].unique()[0]
    colors = load_colors()
    color = colors.get(candidate, {}).get("couleur", "lightgray") if colored else "lightgray"
    opacity = DEFAULT_RAW_MARKER_OPACITY if colored else DEFAULT_GREYED_OPACITY
    
    df_copy = df.copy()
    df_copy["fin_enquete"] = pd.to_datetime(df_copy["fin_enquete"])
    df_copy = df_copy.sort_values("fin_enquete")
    
    segments = _detect_time_segments(df_copy, max_gap_days)
    
    for segment_df in segments:
        _add_raw_data_markers(fig, segment_df, candidate, col_intention, color, opacity, row, col)

    return fig


def plot_intention_data(
    df: pd.DataFrame,
    col_intention: str,
    fig: Optional[go.Figure] = None,
    colored: bool = True,
    row: Optional[int] = None,
    col: Optional[int] = None,
    max_gap_days: int = DEFAULT_MAX_GAP_DAYS,
) -> go.Figure:
    """
    Plot raw intention data points (non-aggregated poll results).
    
    This plots the actual poll data points as scatter markers, providing
    visual context alongside the aggregated rolling average curves.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with raw poll data for a single candidate
    col_intention : str
        Column name for intention values
    fig : Optional[go.Figure], default=None
        Existing figure to add to
    colored : bool, default=True
        Use candidate-specific colors
    row : Optional[int], default=None
        Subplot row number
    col : Optional[int], default=None
        Subplot column number
    max_gap_days : int, default=60
        Maximum gap for segment detection
    
    Returns
    -------
    go.Figure
        Updated figure
    """
    if fig is None:
        fig = go.Figure()

    candidate = df["candidat"].unique()[0]
    colors = load_colors()
    color = colors.get(candidate, {}).get("couleur", "lightgray") if colored else "lightgray"
    opacity = DEFAULT_RAW_MARKER_OPACITY if colored else DEFAULT_GREYED_OPACITY
    
    df_copy = df.copy()
    df_copy["fin_enquete"] = pd.to_datetime(df_copy["fin_enquete"])
    df_copy = df_copy.sort_values("fin_enquete")
    
    segments = _detect_time_segments(df_copy, max_gap_days)
    
    for segment_df in segments:
        if len(segment_df) >= 2 and colored:
            _add_raw_data_line(fig, segment_df, candidate, col_intention, color, row, col)
        
        _add_raw_data_markers(fig, segment_df, candidate, col_intention, color, opacity, row, col)

    return fig


def _should_highlight_candidate(
    candidate: str,
    candidates_to_highlight: Optional[List[str]],
) -> bool:
    """Determine if candidate should be shown in color or greyed out."""
    return (candidates_to_highlight is None) or (candidate in candidates_to_highlight)


def _plot_candidate_curves(
    fig: go.Figure,
    candidate: str,
    df_ranks: pd.DataFrame,
    colored: bool,
) -> go.Figure:
    """Add rolling average curves for a single candidate."""
    df_cand_ranks = df_ranks[df_ranks["candidat"] == candidate]
    
    if not df_cand_ranks.empty:
        fig = plot_intention(df_cand_ranks, col_intention="valeur", fig=fig, colored=colored)
    
    return fig


def _plot_candidate_raw_lines(
    fig: go.Figure,
    candidate: str,
    df_intentions: pd.DataFrame,
    colored: bool,
) -> go.Figure:
    """Add dotted lines connecting raw data points for a single candidate."""
    df_cand_intentions = df_intentions[df_intentions["candidat"] == candidate]
    
    if not df_cand_intentions.empty:
        fig = plot_raw_data_lines(df_cand_intentions, col_intention="intentions", fig=fig, colored=colored)
    
    return fig


def _plot_candidate_raw_markers(
    fig: go.Figure,
    candidate: str,
    df_intentions: pd.DataFrame,
    colored: bool,
) -> go.Figure:
    """Add scatter markers for raw data points for a single candidate."""
    df_cand_intentions = df_intentions[df_intentions["candidat"] == candidate]
    
    if not df_cand_intentions.empty:
        fig = plot_raw_data_markers(df_cand_intentions, col_intention="intentions", fig=fig, colored=colored)
    
    return fig


def _filter_by_date_range(
    df: pd.DataFrame,
    date_range: Optional[Tuple[str, str]],
) -> pd.DataFrame:
    """Filter dataframe by date range if provided."""
    if date_range is None:
        return df
    
    return df[
        (df["fin_enquete"] >= date_range[0]) &
        (df["fin_enquete"] <= date_range[1])
    ]


def _configure_figure_layout(fig: go.Figure, max_value: float) -> go.Figure:
    """Configure axes, title, and logo for the final figure."""
    fig.update_yaxes(
        title="Intention de vote (%)", 
        range=[0, max(40, max_value + 5)]
    )
    fig.update_xaxes(title="Date de fin d'enquête", type="date")
    
    title = "<b>Intentions de vote agrégées (tous scénarios confondus) - Élection présidentielle 2027</b><br>"
    title += f"<sub>Source: presidentielle2027.json | Moyenne mobile sur 14 jours</sub>"
    
    fig.update_layout(
        title=dict(text=title, x=0.5, xanchor="center"),
        width=1400,
        height=800,
        hovermode="closest",
        template="plotly_white",
        images=[
            dict(
                source="https://raw.githubusercontent.com/MieuxVoter/mj-tracker-2027/refs/heads/main/icons/logo.svg",
                xref="paper",
                yref="paper",
                x=0.01,
                y=0.99,
                sizex=0.1,
                sizey=0.1,
                xanchor="left",
                yanchor="top",
                layer="above"
            )
        ]
    )
    
    return fig


def plot_aggregated_intentions(
    smp_data: SMPData,
    candidates_to_highlight: Optional[List[str]] = None,
    date_range: Optional[Tuple[str, str]] = None,
) -> go.Figure:
    """
    Create comprehensive plot of aggregated intentions for all candidates.
    
    This is the main plotting function that combines rolling averages,
    raw data points, error bands, and annotations into a publication-ready
    visualization.
    
    Architecture
    ------------
    This function orchestrates multiple sub-functions to create a layered plot:
    1. plot_intention() - Adds rolling averages with error bands
    2. plot_intention_data() - Adds raw data scatter points
    
    Clean Code Principles Applied
    ------------------------------
    - Single Responsibility: Each function does one thing well
    - Dependency Injection: Takes SMPData object rather than loading data
    - Open/Closed: Easy to extend with new plot types
    - Interface Segregation: Clean, minimal parameters
    
    Parameters
    ----------
    smp_data : SMPData
        Data object containing polling data
    candidates_to_highlight : Optional[List[str]], default=None
        List of candidate names to highlight in color.
        If None, all candidates are highlighted.
        Others are shown in grey.
    date_range : Optional[Tuple[str, str]], default=None
        Date range as (start_date, end_date) strings to filter data
    
    Returns
    -------
    go.Figure
        Complete Plotly figure ready for display or export
    
    Examples
    --------
    >>> from mjtracker.core.smp_data import SMPData
    >>> smp = SMPData()
    >>> fig = plot_aggregated_intentions(smp)
    >>> fig.write_html("output.html")
    
    >>> # Highlight specific candidates
    >>> top_candidates = ["Marine Le Pen", "Jordan Bardella"]
    >>> fig = plot_aggregated_intentions(smp, candidates_to_highlight=top_candidates)
    """
    df_ranks = smp_data.get_ranks()
    df_intentions = smp_data.get_intentions()
    
    df_ranks = _filter_by_date_range(df_ranks, date_range)
    df_intentions = _filter_by_date_range(df_intentions, date_range)
    
    fig = go.Figure()
    all_candidates = df_ranks["candidat"].unique()
    
    # FIRST: Add raw data scatter markers (most important, added first in code = on top visually)
    for candidate in all_candidates:
        colored = _should_highlight_candidate(candidate, candidates_to_highlight)
        fig = _plot_candidate_raw_markers(fig, candidate, df_intentions, colored)
    fig.show()

    # SECOND: Add dotted lines connecting raw data segments
    # TODO: this should be smooth lines (no marker), not dotted lines because we want
    # to show the trend of raw data, not the gaps in raw data
    # for candidate in all_candidates:
    #    colored = _should_highlight_candidate(candidate, candidates_to_highlight)
    #    fig = _plot_candidate_raw_lines(fig, candidate, df_intentions, colored)
    # fig.show()
    
    # THIRD: Add rolling average curves (background layer)
    for candidate in all_candidates:
        colored = _should_highlight_candidate(candidate, candidates_to_highlight)
        fig = _plot_candidate_curves(fig, candidate, df_ranks, colored)
    fig.show()
    fig = _configure_figure_layout(fig, df_ranks["valeur"].max())
    fig.show()
    return fig
