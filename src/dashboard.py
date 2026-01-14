import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Prevent Mac OMP segfaults
os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'

import streamlit as st
import pandas as pd
from src.services.storage import StorageService
from src.services.valuation import ValuationService
from src.services.retrieval import CompRetriever
from src.core.domain.schema import CanonicalListing, GeoLocation
from src.core.domain.models import DBListing

# Page Config
st.set_page_config(page_title="Property Scanner Scout", layout="wide", page_icon="🏠")

@st.cache_resource
def get_services():
    storage = StorageService()
    valuation = ValuationService(storage)
    retriever = CompRetriever()
    return storage, valuation, retriever

storage, valuation, retriever = get_services()

st.title("🏠 Property Scanner Scout")

# --- Sidebar Filters ---
st.sidebar.header("Filters")
min_price, max_price = st.sidebar.slider("Price Range (€)", 0, 2000000, (100000, 1000000), step=10000)
min_score = st.sidebar.slider("Min Deal Score", 0.0, 1.0, 0.5, step=0.05)

# --- Load Data ---
session = storage.get_session()
df = pd.DataFrame()
try:
    # Filter by City Strategy
    available_cities = [c[0] for c in session.query(DBListing.city).distinct().all() if c[0]]
    available_cities.sort()
    
    selected_city = st.sidebar.selectbox("Filter by City", ["All"] + available_cities)
    
    # Query Builder
    query = session.query(DBListing)
    if selected_city != "All":
        query = query.filter(DBListing.city == selected_city)
    
    # Fetch filtered listings
    listings_db = query.all()
    
    # Convert to Domain Objects & Score on the Fly
    data = []
    
    # Initialize progress bar for nice UX
    if listings_db:
        progress_bar = st.progress(0, text="Analyzing Opportunities...")
    
    for i, db_item in enumerate(listings_db):
        # Reconstruct Canonical (simplified)
        loc = GeoLocation(
            lat=db_item.lat, 
            lon=db_item.lon, 
            address_full=db_item.address_full or "Unknown Address",
            city=db_item.city or "Unknown",
            country="ES" 
        ) if db_item.lat else None
        
        listing = CanonicalListing(
            id=db_item.id,
            source_id=db_item.source_id,
            external_id=db_item.external_id,
            url=str(db_item.url),
            title=db_item.title,
            description=db_item.description, # Ensure description flows through
            price=db_item.price,
            property_type=db_item.property_type or "apartment",
            bedrooms=db_item.bedrooms,
            surface_area_sqm=db_item.surface_area_sqm,
            location=loc,
            image_urls=db_item.image_urls
        )
        
        # Lazy Valuation Check
        from src.services.valuation_persister import ValuationPersister
        from src.services.valuation import DealAnalysis
        from src.core.domain.schema import ValuationProjection, EvidencePack
        
        persister = ValuationPersister(session)
        cached_val = persister.get_latest_valuation(db_item.id)
        
        if cached_val:
            # Reconstruct Analysis from Cache (Lite Version)
            projections = [ValuationProjection(**p) for p in cached_val.evidence.get("projections", [])]
            rent_projections = [ValuationProjection(**p) for p in cached_val.evidence.get("rent_projections", [])]
            yield_projections = [ValuationProjection(**p) for p in cached_val.evidence.get("yield_projections", [])]
            analysis = DealAnalysis(
                property_id=db_item.id,
                listing_id=db_item.id,
                fair_value_estimate=cached_val.fair_value,
                fair_value_uncertainty_pct=0.10, # Placeholder or from price_range
                deal_score=cached_val.confidence_score, # Mapping confidence to score for demo
                investment_thesis=cached_val.evidence.get("thesis", "Cached Analysis"),
                market_signals=cached_val.evidence.get("signals", {}),
                projections=projections,
                rent_projections=rent_projections,
                yield_projections=yield_projections,
                evidence=None # Simplified for UI
            )
            comps = [] # Can't easily reconstruct comps list without full deserialization
        else:
             # Live Valuation Fallback
            comps = retriever.retrieve_comps(listing, k=3)
            analysis = valuation.evaluate_deal(listing, comps=comps)

        data.append({
            "ID": listing.id,
            "Title": listing.title,
            "Price": listing.price,
            "Sqm": listing.surface_area_sqm,
            "Bedrooms": listing.bedrooms,
            "City": db_item.city,
            "Deal Score": analysis.deal_score,
            "Fair Value": analysis.fair_value_estimate,
            "Thesis": analysis.investment_thesis,
            "URL": str(listing.url),
            "lat": listing.location.lat if listing.location else None,
            "lon": listing.location.lon if listing.location else None,
            "Image": listing.image_urls[0] if listing.image_urls else None,
            "Images": listing.image_urls,
            "Desc": listing.description,
            "VLM Desc": listing.vlm_description,
            "Projections": analysis.projections,
            "Rent Projections": getattr(analysis, "rent_projections", []),
            "Yield Projections": getattr(analysis, "yield_projections", []),
            "Signals": analysis.market_signals,
            "Comps": comps if comps else [] # Handle empty for cached
        })
        
        if listings_db:
            progress_bar.progress((i + 1) / len(listings_db))
        
    df = pd.DataFrame(data)
    
    if listings_db:
        progress_bar.empty()

finally:
    session.close()

if df.empty:
    st.warning("No listings found in database.")
else:
    # --- Filter Data ---
    filtered_df = df[
        (df["Price"] >= min_price) & 
        (df["Price"] <= max_price) &
        (df["Deal Score"] >= min_score)
    ]

    # --- KPIs ---
    c1, c2, c3 = st.columns(3)
    c1.metric("Listings Found", len(filtered_df))
    if not filtered_df.empty:
        c2.metric("Avg Price", f"{filtered_df['Price'].mean():,.0f} €")
        c3.metric("Top Deal Score", f"{filtered_df['Deal Score'].max():.2f}")

    # --- Tabs ---
    tab1, tab2 = st.tabs(["🗺️ Map View", "📄 List View"])

    with tab1:
        # Streamlit Map requires lat/lon columns and no NaNs
        map_data = filtered_df.dropna(subset=['lat', 'lon']).copy()
        
        if not map_data.empty:
            # Assign colors based on City
            unique_cities = map_data['City'].unique()
            # Simple palette generator (hash based or cycle)
            import random
            
            # Fixed seed for consistency
            def get_color(name):
                random.seed(name)
                return [random.randint(50, 255), random.randint(50, 255), random.randint(50, 255), 200]
            
            city_colors = {city: get_color(city) for city in unique_cities}
            map_data['color'] = map_data['City'].map(city_colors)
            
            import pydeck as pdk
            
            st.pydeck_chart(pdk.Deck(
                map_style='mapbox://styles/mapbox/light-v9',
                initial_view_state=pdk.ViewState(
                    latitude=map_data['lat'].mean(),
                    longitude=map_data['lon'].mean(),
                    zoom=11,
                    pitch=50,
                ),
                layers=[
                    pdk.Layer(
                        'ScatterplotLayer',
                        data=map_data,
                        get_position='[lon, lat]',
                        get_color='color',
                        get_radius=200,
                        pickable=True,
                        auto_highlight=True
                    ),
                ],
                tooltip={"html": "<b>{Title}</b><br/>{City}<br/>{Price:.0f}€", "style": {"backgroundColor": "steelblue", "color": "white"}}
            ))
            
            # Legend
            st.caption("City Legend:")
            legend_cols = st.columns(len(unique_cities)) if len(unique_cities) < 6 else st.columns(6)
            for i, city in enumerate(unique_cities):
                col = legend_cols[i % 6]
                c = city_colors[city]
                col.color_picker(city, f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}", disabled=True, key=f"legend_{i}")
                
        else:
            st.info("No geocoded listings to display on map. (Are you running 'IdealistaNormalizer' correctly?)")

    with tab2:
        # Display Table with key columns
        display_cols = ["Title", "Price", "Sqm", "Deal Score", "Fair Value", "Thesis", "URL"]
        st.dataframe(
            filtered_df[display_cols].style.format({
                "Price": "{:,.0f} €", 
                "Fair Value": "{:,.0f} €",
                "Deal Score": "{:.2f}", 
                "Sqm": "{:.0f}"
            }),
            use_container_width=True
        )

    # --- Details Section ---
    st.markdown("---")
    st.subheader("🧐 Deal Inspector")
    
    if not filtered_df.empty:
        selected_id = st.selectbox("Select Property to Inspect", filtered_df["Title"].unique())
        if selected_id:
            item = filtered_df[filtered_df["Title"] == selected_id].iloc[0]
            
            c_left, c_right = st.columns([1, 2])
            
            with c_left:
                if item["Images"]:
                    # Create a carousel-like experience using tabs or just a list of images
                    # Or just the main image for now with an expander for more
                    st.image(str(item["Images"][0]), use_column_width=True, caption="Main Image")
                    with st.expander(f"📷 See {len(item['Images'])} Photos"):
                        for img in item["Images"]:
                            st.image(str(img), use_column_width=True)
                else:
                    st.markdown("📷 *No Image Available*")
                
                # Market Signals
                if item["Signals"]:
                    st.markdown("### 📡 Market Signals")
                    s1, s2 = st.columns(2)
                    mom = item["Signals"].get("momentum", 0)
                    liq = item["Signals"].get("liquidity", 0)
                    s1.metric("Momentum", f"{mom:+.2f}", delta_color="normal")
                    s2.metric("Liquidity", f"{liq:.2f}")

            with c_right:
                st.write(f"**Price:** {item['Price']:,.0f} €")
                st.write(f"**Fair Value:** {item['Fair Value']:,.0f} €")
                st.write(f"**Score:** {item['Deal Score']:.2f}")
                
                st.info(f"**Thesis:** {item['Thesis']}")
                
                # Descriptions Tab
                tab_desc, tab_vlm = st.tabs(["📄 Original Description", "👁️ AI Vision Analysis"])
                
                with tab_desc:
                    st.text_area("Source Text", item.get("Desc", "No description available."), height=150)
                
                with tab_vlm:
                    if item["VLM Desc"]:
                        st.markdown(f"> *{item['VLM Desc']}*")
                    else:
                        st.caption("No visual analysis available.")
                
                st.markdown(f"[View Listing]({item['URL']})")
                
                # Future Projections Chart
                if item["Projections"]:
                    st.markdown("### 📈 Future Value Projection")
                    proj_data = []
                    # Add current
                    proj_data.append({"Month": 0, "Value": item["Price"], "Type": "Current"})
                    for p in item["Projections"]:
                        proj_data.append({"Month": p.months_future, "Value": p.predicted_value, "Type": "Forecast"})
                        # Add bounds?
                    
                    chart_df = pd.DataFrame(proj_data)
                    st.line_chart(chart_df, x="Month", y="Value")

                if item.get("Rent Projections"):
                    st.markdown("### 🏠 Future Rent Projection (€/month)")
                    rent_data = []
                    for p in item["Rent Projections"]:
                        rent_data.append({"Month": p.months_future, "Rent": p.predicted_value})
                    rent_df = pd.DataFrame(rent_data)
                    if not rent_df.empty:
                        st.line_chart(rent_df, x="Month", y="Rent")

                if item.get("Yield Projections"):
                    st.markdown("### 💸 Future Gross Yield Projection (%)")
                    yield_data = []
                    for p in item["Yield Projections"]:
                        yield_data.append({"Month": p.months_future, "Yield": p.predicted_value})
                    yield_df = pd.DataFrame(yield_data)
                    if not yield_df.empty:
                        st.line_chart(yield_df, x="Month", y="Yield")
                
                # Show Comps
                if item["Comps"]:
                    with st.expander(f"📚 Evidence: {len(item['Comps'])} Comparable Listings"):
                        for c in item["Comps"]:
                            st.markdown(f"- **{c.similarity_score:.0%} Sim**: {c.price:,.0f}€ ({c.features.get('sqm')}m²) [Snap: {c.id[:8]}]")
