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
    # Fetch all listings
    listings_db = session.query(DBListing).all()
    
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
            address_full=db_item.address_full,
            city=db_item.city or "Unknown",
            country="ES" 
        ) if db_item.lat else None
        
        listing = CanonicalListing(
            id=db_item.id,
            source_id=db_item.source_id,
            external_id=db_item.external_id,
            url=str(db_item.url),
            title=db_item.title,
            price=db_item.price,
            property_type=db_item.property_type or "apartment",
            bedrooms=db_item.bedrooms,
            surface_area_sqm=db_item.surface_area_sqm,
            location=loc,
            image_urls=db_item.image_urls
        )
        
        # Retrieval
        comps = retriever.retrieve_comps(listing, k=3)
        
        # Valuation (with Comps)
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
            "VLM Desc": listing.vlm_description,
            "Projections": analysis.projections,
            "Signals": analysis.market_signals,
            "Comps": comps # Store for UI
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
        map_data = filtered_df.dropna(subset=['lat', 'lon'])
        if not map_data.empty:
            st.map(map_data, size=20, color="#00ff00") # Green dots
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
                    st.image(item["Images"][0], use_column_width=True, caption="Main Image")
                    with st.expander(f"📷 See {len(item['Images'])} Photos"):
                        for img in item["Images"]:
                            st.image(img, use_column_width=True)
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
                
                # VLM Description
                if item["VLM Desc"]:
                    st.markdown(f"**👁️ AI Vision Analysis:**\n> *{item['VLM Desc']}*")
                
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
                
                # Show Comps
                if item["Comps"]:
                    with st.expander(f"📚 Evidence: {len(item['Comps'])} Comparable Listings"):
                        for c in item["Comps"]:
                            st.markdown(f"- **{c.similarity_score:.0%} Sim**: {c.price:,.0f}€ ({c.features.get('sqm')}m²) [Snap: {c.id[:8]}]")
