from typing import List, Tuple
import pandas as pd

from src.interfaces.dashboard.utils.formatting import format_budget_range

def build_lens_chips(
    selected_country: str,
    selected_city: str,
    selected_types: List[str],
    min_price: float,
    max_price: float,
    default_range: Tuple[int, int],
    available_types: List[str],
) -> List[str]:
    """Builds a list of filter chips to display."""
    chips: List[str] = []
    if selected_city and selected_city != "All":
        chips.append(selected_city)
    elif selected_country and selected_country != "All":
        chips.append(selected_country)

    if selected_types and len(selected_types) < len(available_types):
        if len(selected_types) <= 2:
            chips.append(", ".join(selected_types))
        else:
            chips.append(f"{len(selected_types)} types")

    if (min_price, max_price) != default_range:
        chips.append(format_budget_range(min_price, max_price))

    if not chips:
        chips.append("All markets")
    return chips


def resolve_plotly_selection(selection, data: pd.DataFrame, id_col: str = "ID") -> pd.DataFrame:
    """Filters dataframe based on Plotly selection event."""
    if selection is None or data.empty:
        return data.iloc[0:0]
    selection_data = getattr(selection, "selection", None)
    if not isinstance(selection_data, dict):
        return data.iloc[0:0]
    points = selection_data.get("points") or []
    if not points:
        return data.iloc[0:0]
    selected_ids = []
    for point in points:
        custom = point.get("customdata") if isinstance(point, dict) else None
        if isinstance(custom, (list, tuple)) and custom:
            selected_ids.append(str(custom[0]))
    if not selected_ids:
        return data.iloc[0:0]
    return data[data[id_col].astype(str).isin(selected_ids)]
