import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import Map, { Marker } from "react-map-gl/maplibre"
import maplibregl from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"
import { motion, AnimatePresence } from "framer-motion"
import {
    Satellite, Battery, Zap, Activity, Crosshair, X,
    Leaf, Droplets, RefreshCw, Search, Loader2,
    ChevronRight, MapPin, Gauge, TrendingDown, TrendingUp,
    Shield, BarChart2, Layers, CloudRain, ImageIcon
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"

const API = "http://localhost:8000"

// Free map tiles — no API key required
const MAP_STYLE_DARK = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
const MAP_STYLE_SAT: any = {
    version: 8,
    sources: {
        "esri-satellite": {
            type: "raster",
            tiles: [
                "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
            ],
            tileSize: 256,
            attribution: "© Esri"
        }
    },
    layers: [
        {
            id: "esri-satellite-layer",
            type: "raster",
            source: "esri-satellite",
            minzoom: 0,
            maxzoom: 19
        }
    ]
}

interface LocationData {
    loc_id: string
    name: string
    lat: number
    lon: number
    households: number
    latest_run_id: string | null
}

interface SatelliteData {
    preview_url: string | null
    scene_date: string | null
    cloud_cover_pct: number | null
    ndvi_mean: number | null
    ndwi_mean: number | null
    ndvi_vegetation_pct: number | null
    ndvi_urban_pct: number | null
    water_coverage_pct: number | null
    settlement_density: string | null
    land_cover_summary: string[]
    scl_quality: {
        usable_pct: number; cloud_pct: number; shadow_pct: number
        vegetation_pct: number; buildup_soil_pct: number; water_pct: number
    } | null
    ndvi_change: {
        delta_mean: number; loss_pct: number; gain_pct: number; compared_to_date: string
    } | null
    sentinel_scene_count: number
    ndvi_image: string | null
    ndwi_image: string | null
    error: string | null
    data_unavailable: boolean
}

interface SearchSatResult extends SatelliteData {
    location_name: string
    lat: number
    lon: number
    quality_flags: string[]
}

interface GeoResult {
    name: string
    lat: number
    lon: number
}

interface DashboardStats {
    total_locations: number
    total_households: number
    total_runs: number
    avg_confidence: number
}

function MarkerDot({ confidence, active }: { confidence?: number; active?: boolean }) {
    const c = confidence ?? 0
    const color = c >= 0.7 ? "#22c55e" : c >= 0.5 ? "#eab308" : c > 0 ? "#ef4444" : "#3b82f6"
    return (
        <div className="relative cursor-pointer group">
            <div className={`h-4 w-4 rounded-full border-2 border-white/80 shadow-lg transition-transform ${active ? "scale-150" : "group-hover:scale-125"}`}
                style={{ background: color, boxShadow: `0 0 12px ${color}80` }} />
            {active && <div className="absolute h-4 w-4 rounded-full animate-ping opacity-30" style={{ background: color }} />}
        </div>
    )
}

export default function Dashboard() {
    const navigate = useNavigate()
    const [locations, setLocations] = useState<LocationData[]>([])
    const [stats, setStats] = useState<DashboardStats | null>(null)
    const [selectedLocId, setSelectedLocId] = useState<string | null>(null)
    const [locDetails, setLocDetails] = useState<any>(null)
    const [satData, setSatData] = useState<SatelliteData | null>(null)
    const [showSat, setShowSat] = useState(false)
    const [satView, setSatView] = useState<"true-color" | "ndvi" | "ndwi">("true-color")
    const [reanalyzing, setReanalyzing] = useState(false)
    const [viewState, setViewState] = useState({
        longitude: 36.8, latitude: -1.2, zoom: 4
    })

    // Search state
    const [searchQuery, setSearchQuery] = useState("")
    const [searching, setSearching] = useState(false)
    const [searchAnalyzing, setSearchAnalyzing] = useState(false)
    const [searchResult, setSearchResult] = useState<SearchSatResult | null>(null)
    const [geoResults, setGeoResults] = useState<GeoResult[]>([])
    const [searchError, setSearchError] = useState<string | null>(null)

    useEffect(() => {
        fetch(`${API}/api/locations`).then(res => res.json())
            .then(data => setLocations(data.locations || [])).catch(console.error)
        fetch(`${API}/api/dashboard/stats`).then(res => res.json())
            .then(setStats).catch(console.error)
    }, [])

    useEffect(() => {
        if (!selectedLocId) {
            setLocDetails(null); setSatData(null); setShowSat(false); setSatView("true-color"); return
        }
        // Clear search when selecting a saved location
        setSearchResult(null); setGeoResults([])
        const loc = locations.find(l => l.loc_id === selectedLocId)
        if (loc) setViewState(prev => ({ ...prev, longitude: loc.lon, latitude: loc.lat, zoom: 14 }))
        fetch(`${API}/api/locations/${selectedLocId}`).then(res => res.json()).then(setLocDetails).catch(console.error)
        fetch(`${API}/api/locations/${selectedLocId}/satellite`).then(res => res.json()).then(setSatData).catch(console.error)
    }, [selectedLocId, locations])

    // Search handlers
    const handleSearch = async () => {
        if (!searchQuery.trim()) return
        setSearchError(null); setGeoResults([])
        // Check if coordinates
        const coordMatch = searchQuery.match(/^\s*(-?\d+\.?\d*)\s*[,\s]\s*(-?\d+\.?\d*)\s*$/)
        if (coordMatch) {
            const lat = parseFloat(coordMatch[1]), lon = parseFloat(coordMatch[2])
            if (lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180) {
                await runSatSearch(lat, lon, `${lat.toFixed(4)}, ${lon.toFixed(4)}`)
                return
            }
        }
        setSearching(true)
        try {
            const res = await fetch(`${API}/api/geocode?q=${encodeURIComponent(searchQuery)}`)
            const data = await res.json()
            if (data.length === 0) setSearchError("No locations found. Try coordinates (lat, lon).")
            else if (data.length === 1) await runSatSearch(data[0].lat, data[0].lon, data[0].name)
            else setGeoResults(data)
        } catch { setSearchError("Geocoding failed. Try coordinates (e.g. 51.50, -0.18).") }
        finally { setSearching(false) }
    }

    const runSatSearch = async (lat: number, lon: number, name: string) => {
        setSelectedLocId(null); setLocDetails(null); setSatData(null)
        setGeoResults([]); setSearchAnalyzing(true); setSearchError(null)
        setSearchResult(null); setSatView("true-color")
        setViewState(prev => ({ ...prev, longitude: lon, latitude: lat, zoom: 12 }))
        try {
            const res = await fetch(`${API}/api/satellite/search`, {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ lat, lon, location_name: name })
            })
            if (!res.ok) { const e = await res.json().catch(() => ({ detail: "Error" })); throw new Error(e.detail) }
            setSearchResult(await res.json())
        } catch (e: any) { setSearchError(e.message || "Analysis failed") }
        finally { setSearchAnalyzing(false) }
    }

    const handleReanalyze = async () => {
        if (!selectedLocId || reanalyzing) return
        setReanalyzing(true)
        try {
            await fetch(`${API}/api/locations/${selectedLocId}/reanalyze`, { method: "POST" })
            const [det, sat] = await Promise.all([
                fetch(`${API}/api/locations/${selectedLocId}`).then(r => r.json()),
                fetch(`${API}/api/locations/${selectedLocId}/satellite`).then(r => r.json()),
            ])
            setLocDetails(det); setSatData(sat)
        } finally { setReanalyzing(false) }
    }

    const plan = locDetails?.latest_run?.outputs?.scenario_set?.primary
    const quality = locDetails?.latest_run?.outputs?.quality || {}
    const impact = locDetails?.latest_run?.outputs?.impact_metrics || {}

    return (
        <div className="flex h-full w-full overflow-hidden bg-background">
            {/* Left Sidebar */}
            <div className="w-80 border-r border-white/10 bg-card/50 flex flex-col backdrop-blur-md z-10 shrink-0">
                {/* Stats Header */}
                {stats && (
                    <div className="p-4 border-b border-white/10 bg-primary/5">
                        <div className="grid grid-cols-2 gap-2 text-center">
                            <div>
                                <div className="text-xl font-bold text-primary">{stats.total_locations}</div>
                                <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Sites</div>
                            </div>
                            <div>
                                <div className="text-xl font-bold text-secondary">{stats.total_households.toLocaleString()}</div>
                                <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Households</div>
                            </div>
                            <div>
                                <div className="text-xl font-bold text-accent">{stats.total_runs}</div>
                                <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Runs</div>
                            </div>
                            <div>
                                <div className="text-xl font-bold text-yellow-400">{(stats.avg_confidence * 100).toFixed(0)}%</div>
                                <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Avg Conf</div>
                            </div>
                        </div>
                    </div>
                )}

                {/* Search Bar */}
                <div className="p-3 border-b border-white/10">
                    <div className="relative">
                        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                        <input
                            placeholder="Search any location…"
                            value={searchQuery}
                            onChange={e => setSearchQuery(e.target.value)}
                            onKeyDown={e => e.key === "Enter" && handleSearch()}
                            className="w-full pl-8 pr-8 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary/50 transition-colors"
                        />
                        {(searching || searchAnalyzing) ? (
                            <Loader2 className="absolute right-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-primary animate-spin" />
                        ) : searchQuery && (
                            <button onClick={() => { setSearchQuery(""); setSearchResult(null); setSearchError(null); setGeoResults([]) }}
                                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                                <X className="h-3.5 w-3.5" />
                            </button>
                        )}
                    </div>
                    {/* Geocode dropdown */}
                    {geoResults.length > 1 && (
                        <div className="mt-1.5 bg-card border border-white/10 rounded-lg overflow-hidden shadow-xl">
                            {geoResults.slice(0, 5).map((g, i) => (
                                <button key={i} onClick={() => runSatSearch(g.lat, g.lon, g.name)}
                                    className="w-full text-left px-3 py-2 hover:bg-white/5 transition-colors border-b border-white/5 last:border-0 text-xs">
                                    <div className="flex items-center gap-1.5">
                                        <MapPin className="h-3 w-3 text-primary shrink-0" />
                                        <span className="truncate">{g.name}</span>
                                    </div>
                                </button>
                            ))}
                        </div>
                    )}
                    {searchError && (
                        <div className="mt-1.5 text-xs text-red-400 px-1">{searchError}</div>
                    )}
                </div>

                <div className="p-4 border-b border-white/10 flex items-center gap-3">
                    <Activity className="text-primary h-5 w-5" />
                    <h2 className="font-semibold text-lg tracking-wide">Monitor List</h2>
                </div>
                <div className="flex-1 overflow-y-auto p-4 space-y-2">
                    {locations.map((loc) => (
                        <button key={loc.loc_id} onClick={() => setSelectedLocId(loc.loc_id)}
                            className={`w-full text-left p-4 rounded-xl border transition-all duration-300 ${selectedLocId === loc.loc_id
                                ? "border-primary bg-primary/10 neon-glow"
                                : "border-white/5 hover:border-white/20 hover:bg-white/5"}`}
                        >
                            <div className="flex items-center gap-2">
                                <MapPin className="h-3.5 w-3.5 text-primary shrink-0" />
                                <span className="font-medium">{loc.name}</span>
                            </div>
                            <div className="text-xs text-muted-foreground mt-1 flex gap-2 ml-5">
                                <span>{loc.households} HH</span>
                                <span>•</span>
                                <span>{loc.lat.toFixed(2)}, {loc.lon.toFixed(2)}</span>
                            </div>
                        </button>
                    ))}
                    {locations.length === 0 && (
                        <div className="text-sm text-muted-foreground p-4 text-center">
                            No active sites. Go to Studio to deploy an AI agent.
                        </div>
                    )}
                </div>
            </div>

            {/* Main Content Area */}
            <div className="relative flex-1 bg-black overflow-hidden">
                {/* Map — always visible, toggles between dark and satellite tiles */}
                <div className="absolute inset-0 z-0">
                    <Map
                        {...viewState}
                        onMove={(evt) => setViewState(evt.viewState)}
                        mapStyle={showSat ? MAP_STYLE_SAT : MAP_STYLE_DARK}
                        mapLib={maplibregl as any}
                        style={{ width: "100%", height: "100%" }}
                    >
                        {locations.map(loc => (
                            <Marker key={loc.loc_id} longitude={loc.lon} latitude={loc.lat} anchor="center"
                                onClick={(e) => { e.originalEvent.stopPropagation(); setSelectedLocId(loc.loc_id) }}>
                                <MarkerDot confidence={quality.confidence} active={selectedLocId === loc.loc_id} />
                            </Marker>
                        ))}
                    </Map>
                    {showSat && (
                        <div className="absolute top-6 left-6 bg-black/70 px-4 py-2 rounded-lg border border-primary/40 backdrop-blur-md text-primary text-sm font-mono flex items-center gap-2 z-10">
                            <Crosshair className="h-4 w-4" />SATELLITE VIEW
                        </div>
                    )}
                </div>

                {/* Slide-in Summary Panel */}
                <AnimatePresence>
                    {selectedLocId && locDetails && (
                        <motion.div
                            initial={{ x: "100%", opacity: 0 }}
                            animate={{ x: 0, opacity: 1 }}
                            exit={{ x: "100%", opacity: 0 }}
                            transition={{ type: "spring", damping: 25, stiffness: 200 }}
                            className="absolute right-0 top-0 bottom-0 w-[460px] glass-panel border-l border-t-0 border-b-0 border-r-0 z-20 flex flex-col"
                        >
                            <div className="p-6 flex items-center justify-between border-b border-white/10">
                                <div>
                                    <h3 className="font-bold text-xl">{locDetails.location?.name}</h3>
                                    {quality.confidence != null && (
                                        <div className="mt-1 flex items-center gap-2 text-xs">
                                            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border font-mono font-bold
                                                ${quality.confidence >= 0.7 ? "text-green-400 border-green-400/30 bg-green-400/10"
                                                    : quality.confidence >= 0.5 ? "text-yellow-400 border-yellow-400/30 bg-yellow-400/10"
                                                        : "text-red-400 border-red-400/30 bg-red-400/10"}`}>
                                                <Gauge className="h-3 w-3" /> {Math.round(quality.confidence * 100)}%
                                            </span>
                                            {quality.fallback_used && (
                                                <span className="text-yellow-400 text-[10px]">FALLBACK</span>
                                            )}
                                        </div>
                                    )}
                                </div>
                                <Button variant="ghost" size="icon" onClick={() => setSelectedLocId(null)}>
                                    <X className="h-5 w-5" />
                                </Button>
                            </div>

                            <div className="flex-1 overflow-y-auto p-6 space-y-6">

                                {/* Action Buttons */}
                                <div className="grid grid-cols-3 gap-2">
                                    <Button variant={showSat ? "default" : "outline"} className="w-full text-xs h-10"
                                        onClick={() => setShowSat(!showSat)}>
                                        <Satellite className="mr-1 h-3 w-3" />
                                        {showSat ? "Hide Sat" : "Satellite"}
                                    </Button>
                                    <Button variant="outline" className="w-full text-xs h-10"
                                        onClick={handleReanalyze} disabled={reanalyzing}>
                                        <RefreshCw className={`mr-1 h-3 w-3 ${reanalyzing ? "animate-spin" : ""}`} />
                                        {reanalyzing ? "Run…" : "Re-run"}
                                    </Button>
                                    <Button variant="outline" className="w-full text-xs h-10 text-primary border-primary/30 hover:bg-primary/10"
                                        onClick={() => navigate(`/location/${selectedLocId}`)}>
                                        Full View <ChevronRight className="ml-1 h-3 w-3" />
                                    </Button>
                                </div>

                                {/* Impact Quick Cards */}
                                {Object.keys(impact).length > 0 && (
                                    <div className="grid grid-cols-2 gap-2">
                                        <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-3 text-center">
                                            <div className="text-lg font-bold text-green-400">{(impact.co2_avoided_tons_estimate || 0).toFixed(1)}t</div>
                                            <div className="text-[10px] text-muted-foreground uppercase">CO₂ Avoided/yr</div>
                                        </div>
                                        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-3 text-center">
                                            <div className="text-lg font-bold text-emerald-400">${(impact.annual_cost_savings_usd_estimate || 0).toLocaleString()}</div>
                                            <div className="text-[10px] text-muted-foreground uppercase">Savings/yr</div>
                                        </div>
                                    </div>
                                )}

                                {/* Satellite Intelligence Quick */}
                                {satData && (
                                    <div className="space-y-3">
                                        <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                                            <Satellite className="h-4 w-4" /> Sentinel-2
                                            {satData.scene_date && <span className="text-xs font-mono text-primary/70 ml-auto">{satData.scene_date}</span>}
                                        </h4>

                                        {/* Data Unavailable Banner */}
                                        {satData.data_unavailable && (
                                            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 text-center">
                                                <Satellite className="h-6 w-6 text-red-400 mx-auto mb-2 opacity-60" />
                                                <div className="text-xs font-semibold text-red-400 mb-1">Unable to Fetch Satellite Data</div>
                                                <div className="text-[10px] text-muted-foreground">
                                                    {satData.error || "Sentinel-2 imagery could not be retrieved. Try re-running the analysis."}
                                                </div>
                                            </div>
                                        )}

                                        {!satData.data_unavailable && (<>

                                        {(satData.preview_url || satData.ndvi_image || satData.ndwi_image) && (
                                            <div className="flex gap-1">
                                                {satData.preview_url && (
                                                    <button onClick={() => { setSatView("true-color"); setShowSat(true) }}
                                                        className={`flex-1 text-xs py-1.5 px-2 rounded border transition-all ${satView === "true-color" && showSat ? "border-primary/60 bg-primary/20 text-primary" : "border-white/10 bg-white/5 text-muted-foreground hover:border-white/30"}`}>
                                                        True Color</button>
                                                )}
                                                {satData.ndvi_image && (
                                                    <button onClick={() => { setSatView("ndvi"); setShowSat(true) }}
                                                        className={`flex-1 text-xs py-1.5 px-2 rounded border transition-all ${satView === "ndvi" && showSat ? "border-green-400/60 bg-green-400/20 text-green-400" : "border-white/10 bg-white/5 text-muted-foreground hover:border-white/30"}`}>
                                                        NDVI</button>
                                                )}
                                                {satData.ndwi_image && (
                                                    <button onClick={() => { setSatView("ndwi"); setShowSat(true) }}
                                                        className={`flex-1 text-xs py-1.5 px-2 rounded border transition-all ${satView === "ndwi" && showSat ? "border-blue-400/60 bg-blue-400/20 text-blue-400" : "border-white/10 bg-white/5 text-muted-foreground hover:border-white/30"}`}>
                                                        NDWI</button>
                                                )}
                                            </div>
                                        )}

                                        <div className="grid grid-cols-2 gap-2">
                                            <div className="bg-white/5 border border-white/10 rounded-lg p-3">
                                                <div className="flex items-center gap-1 text-xs text-muted-foreground mb-1"><Leaf className="h-3 w-3 text-green-400" /> NDVI</div>
                                                <div className="text-xl font-bold text-green-400">{satData.ndvi_mean != null ? satData.ndvi_mean.toFixed(3) : "—"}</div>
                                                <div className="text-xs text-muted-foreground mt-1">{satData.ndvi_vegetation_pct != null ? `${satData.ndvi_vegetation_pct.toFixed(0)}% vegetation` : ""}</div>
                                            </div>
                                            <div className="bg-white/5 border border-white/10 rounded-lg p-3">
                                                <div className="flex items-center gap-1 text-xs text-muted-foreground mb-1"><Droplets className="h-3 w-3 text-blue-400" /> NDWI</div>
                                                <div className="text-xl font-bold text-blue-400">{satData.ndwi_mean != null ? satData.ndwi_mean.toFixed(3) : "—"}</div>
                                                <div className="text-xs text-muted-foreground mt-1">{satData.water_coverage_pct != null ? `${satData.water_coverage_pct.toFixed(1)}% water` : ""}</div>
                                            </div>
                                        </div>

                                        {/* No data message */}
                                        {!satData.preview_url && !satData.ndvi_image && satData.ndvi_mean == null && !satData.data_unavailable && (
                                            <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-3 text-center text-xs text-yellow-400">
                                                Satellite data not yet available. Click "Re-run" to fetch Sentinel-2 imagery from Planetary Computer.
                                            </div>
                                        )}
                                        </>)}
                                    </div>
                                )}

                                {/* Energy Spec Cards */}
                                {plan && (
                                    <div className="space-y-3 pt-2 border-t border-white/10">
                                        <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">Energy Blueprint</h4>
                                        <div className="grid grid-cols-2 gap-3">
                                            <Card className="bg-white/5 border-white/10">
                                                <CardHeader className="p-4 pb-2">
                                                    <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                                                        <Zap className="h-4 w-4 text-primary" /> PV Array
                                                    </CardTitle>
                                                </CardHeader>
                                                <CardContent className="p-4 pt-0">
                                                    <span className="text-2xl font-bold">{plan.pv_kw}</span> <span className="text-sm">kW</span>
                                                </CardContent>
                                            </Card>
                                            <Card className="bg-white/5 border-white/10">
                                                <CardHeader className="p-4 pb-2">
                                                    <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                                                        <Battery className="h-4 w-4 text-secondary" /> Battery
                                                    </CardTitle>
                                                </CardHeader>
                                                <CardContent className="p-4 pt-0">
                                                    <span className="text-2xl font-bold">{plan.battery_kwh}</span> <span className="text-sm">kWh</span>
                                                </CardContent>
                                            </Card>
                                        </div>
                                    </div>
                                )}

                                {/* View Full Analysis CTA */}
                                <Button className="w-full h-12 neon-glow text-sm font-bold tracking-wider"
                                    onClick={() => navigate(`/location/${selectedLocId}`)}>
                                    View Full Analysis <ChevronRight className="ml-2 h-4 w-4" />
                                </Button>

                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        </div>
    )
}
