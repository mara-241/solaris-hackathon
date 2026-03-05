
import { useEffect, useState } from "react"
import Map, { Marker } from "react-map-gl"
import type { ViewState } from "react-map-gl"
import "mapbox-gl/dist/mapbox-gl.css"
import { motion, AnimatePresence } from "framer-motion"
import { Satellite, Battery, Zap, Activity, Shield, Crosshair, X, Clock, Leaf, Droplets, TrendingDown, TrendingUp, BarChart2, RefreshCw } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;

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
        usable_pct: number
        cloud_pct: number
        shadow_pct: number
        vegetation_pct: number
        buildup_soil_pct: number
        water_pct: number
    } | null
    ndvi_change: {
        delta_mean: number
        loss_pct: number
        gain_pct: number
        compared_to_date: string
    } | null
    sentinel_scene_count: number
    ndvi_image: string | null
    ndwi_image: string | null
}

export default function Dashboard() {
    const [locations, setLocations] = useState<LocationData[]>([])
    const [selectedLocId, setSelectedLocId] = useState<string | null>(null)
    const [locDetails, setLocDetails] = useState<any>(null)
    const [satData, setSatData] = useState<SatelliteData | null>(null)
    const [showSat, setShowSat] = useState(false)
    const [satView, setSatView] = useState<"true-color" | "ndvi" | "ndwi">("true-color")
    const [reanalyzing, setReanalyzing] = useState(false)
    const [viewState, setViewState] = useState<Partial<ViewState>>({
        longitude: 36.8,
        latitude: -1.2,
        zoom: 4
    })

    useEffect(() => {
        fetch("http://localhost:8001/api/locations")
            .then(res => res.json())
            .then(data => setLocations(data.locations || []))
            .catch(console.error)
    }, [])

    useEffect(() => {
        if (!selectedLocId) {
            setLocDetails(null)
            setSatData(null)
            setShowSat(false)
            setSatView("true-color")
            return
        }

        const loc = locations.find(l => l.loc_id === selectedLocId)
        if (loc) {
            setViewState((prev: any) => ({ ...prev, longitude: loc.lon, latitude: loc.lat, zoom: 14 }))
        }

        fetch(`http://localhost:8001/api/locations/${selectedLocId}`)
            .then(res => res.json())
            .then(data => setLocDetails(data))
            .catch(console.error)

        fetch(`http://localhost:8001/api/locations/${selectedLocId}/satellite`)
            .then(res => res.json())
            .then(data => setSatData(data))
            .catch(console.error)
    }, [selectedLocId, locations])

    const handleReanalyze = async () => {
        if (!selectedLocId || reanalyzing) return
        setReanalyzing(true)
        try {
            await fetch(`http://localhost:8001/api/locations/${selectedLocId}/reanalyze`, { method: "POST" })
            const [det, sat] = await Promise.all([
                fetch(`http://localhost:8001/api/locations/${selectedLocId}`).then(r => r.json()),
                fetch(`http://localhost:8001/api/locations/${selectedLocId}/satellite`).then(r => r.json()),
            ])
            setLocDetails(det)
            setSatData(sat)
        } finally {
            setReanalyzing(false)
        }
    }

    const plan = locDetails?.latest_run?.outputs?.scenario_set?.primary
    const timeline = locDetails?.latest_run?.outputs?.optimization_result?.actionable_timeline || []

    return (
        <div className="flex h-full w-full overflow-hidden bg-background">
            {/* Left Sidebar - Monitor List */}
            <div className="w-80 border-r border-white/10 bg-card/50 flex flex-col backdrop-blur-md z-10 shrink-0">
                <div className="p-6 border-b border-white/10 flex items-center gap-3">
                    <Activity className="text-primary h-5 w-5" />
                    <h2 className="font-semibold text-lg tracking-wide">Monitor List</h2>
                </div>
                <div className="flex-1 overflow-y-auto p-4 space-y-2">
                    {locations.map((loc) => (
                        <button
                            key={loc.loc_id}
                            onClick={() => setSelectedLocId(loc.loc_id)}
                            className={`w-full text-left p-4 rounded-xl border transition-all duration-300 ${selectedLocId === loc.loc_id
                                ? "border-primary bg-primary/10 neon-glow"
                                : "border-white/5 hover:border-white/20 hover:bg-white/5"
                                }`}
                        >
                            <div className="font-medium">{loc.name}</div>
                            <div className="text-xs text-muted-foreground mt-1 flex gap-2">
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
                {/* Map / Satellite Toggle View */}
                {showSat && satData && (satData.preview_url || satData.ndvi_image || satData.ndwi_image) ? (() => {
                    const imgSrc =
                        satView === "ndvi" ? satData.ndvi_image
                        : satView === "ndwi" ? satData.ndwi_image
                        : satData.preview_url
                    const label =
                        satView === "ndvi" ? "NDVI VEGETATION MAP"
                        : satView === "ndwi" ? "NDWI WATER INDEX MAP"
                        : `SENTINEL-2 L2A — ${satData.scene_date || "PLANETARY COMPUTER"}`
                    return imgSrc ? (
                        <motion.div
                            key={satView}
                            initial={{ opacity: 0, scale: 0.98 }}
                            animate={{ opacity: 1, scale: 1 }}
                            className="absolute inset-0 z-0 bg-black flex items-center justify-center"
                        >
                            <img src={imgSrc} alt={label} className="w-full h-full object-contain opacity-95" />
                            <div className="absolute inset-0 border-[10px] border-primary/20 pointer-events-none mix-blend-overlay"></div>
                            <div className="absolute top-6 left-6 bg-black/70 px-4 py-2 rounded-lg border border-primary/40 backdrop-blur-md text-primary text-sm font-mono flex items-center gap-2">
                                <Crosshair className="h-4 w-4" />
                                {label}
                                {satView === "true-color" && satData.cloud_cover_pct != null && (
                                    <span className="text-muted-foreground ml-2">{satData.cloud_cover_pct.toFixed(1)}% cloud</span>
                                )}
                            </div>
                        </motion.div>
                    ) : null
                })() : (
                    <div className="absolute inset-0 z-0">
                        <Map
                            {...viewState}
                            // @ts-ignore - mapbox types conflicting in Vite TS
                            onMove={(evt: any) => setViewState(evt.viewState)}
                            mapStyle={showSat ? "mapbox://styles/mapbox/satellite-streets-v12" : "mapbox://styles/mapbox/dark-v11"}
                            mapboxAccessToken={MAPBOX_TOKEN}
                        >
                            {locations.map(loc => (
                                <Marker key={loc.loc_id} longitude={loc.lon} latitude={loc.lat} />
                            ))}
                        </Map>
                        {showSat && (
                            <div className="absolute top-6 left-6 bg-black/60 px-4 py-2 rounded-lg border border-primary/40 backdrop-blur-md text-primary text-sm font-mono flex items-center gap-2">
                                <Crosshair className="h-4 w-4" />
                                MAPBOX SATELLITE VIEW
                            </div>
                        )}
                    </div>
                )}

                {/* Slide-in Analysis Panel */}
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
                                <h3 className="font-bold text-xl">{locDetails.location?.name}</h3>
                                <Button variant="ghost" size="icon" onClick={() => setSelectedLocId(null)}>
                                    <X className="h-5 w-5" />
                                </Button>
                            </div>

                            <div className="flex-1 overflow-y-auto p-6 space-y-6">

                                {/* Action Buttons */}
                                <div className="grid grid-cols-2 gap-3">
                                    <Button
                                        variant={showSat ? "default" : "outline"}
                                        className="w-full text-xs h-12"
                                        onClick={() => setShowSat(!showSat)}
                                    >
                                        <Satellite className="mr-2 h-4 w-4" />
                                        {showSat ? "Hide Satellite" : "View Satellite"}
                                    </Button>
                                    <Button
                                        variant="outline"
                                        className="w-full text-xs h-12"
                                        onClick={handleReanalyze}
                                        disabled={reanalyzing}
                                    >
                                        <RefreshCw className={`mr-2 h-4 w-4 ${reanalyzing ? "animate-spin" : ""}`} />
                                        {reanalyzing ? "Analyzing…" : "Re-analyze"}
                                    </Button>
                                </div>

                                {/* Sentinel-2 Intelligence */}
                                {satData && (
                                    <div className="space-y-3">
                                        <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                                            <Satellite className="h-4 w-4" /> Sentinel-2 Intelligence
                                            {satData.scene_date && <span className="text-xs font-mono text-primary/70 ml-auto">{satData.scene_date}</span>}
                                        </h4>

                                        {/* Image View Switcher */}
                                        {(satData.preview_url || satData.ndvi_image || satData.ndwi_image) && (
                                            <div className="flex gap-1">
                                                {satData.preview_url && (
                                                    <button
                                                        onClick={() => { setSatView("true-color"); setShowSat(true) }}
                                                        className={`flex-1 text-xs py-1.5 px-2 rounded border transition-all ${
                                                            satView === "true-color" && showSat
                                                                ? "border-primary/60 bg-primary/20 text-primary"
                                                                : "border-white/10 bg-white/5 text-muted-foreground hover:border-white/30"
                                                        }`}
                                                    >
                                                        True Color
                                                    </button>
                                                )}
                                                {satData.ndvi_image && (
                                                    <button
                                                        onClick={() => { setSatView("ndvi"); setShowSat(true) }}
                                                        className={`flex-1 text-xs py-1.5 px-2 rounded border transition-all ${
                                                            satView === "ndvi" && showSat
                                                                ? "border-green-400/60 bg-green-400/20 text-green-400"
                                                                : "border-white/10 bg-white/5 text-muted-foreground hover:border-white/30"
                                                        }`}
                                                    >
                                                        NDVI Map
                                                    </button>
                                                )}
                                                {satData.ndwi_image && (
                                                    <button
                                                        onClick={() => { setSatView("ndwi"); setShowSat(true) }}
                                                        className={`flex-1 text-xs py-1.5 px-2 rounded border transition-all ${
                                                            satView === "ndwi" && showSat
                                                                ? "border-blue-400/60 bg-blue-400/20 text-blue-400"
                                                                : "border-white/10 bg-white/5 text-muted-foreground hover:border-white/30"
                                                        }`}
                                                    >
                                                        NDWI Map
                                                    </button>
                                                )}
                                            </div>
                                        )}

                                        {/* NDVI + NDWI row */}
                                        <div className="grid grid-cols-2 gap-2">
                                            <div className="bg-white/5 border border-white/10 rounded-lg p-3">
                                                <div className="flex items-center gap-1 text-xs text-muted-foreground mb-1">
                                                    <Leaf className="h-3 w-3 text-green-400" /> NDVI
                                                </div>
                                                <div className="text-xl font-bold text-green-400">
                                                    {satData.ndvi_mean != null ? satData.ndvi_mean.toFixed(3) : "—"}
                                                </div>
                                                <div className="text-xs text-muted-foreground mt-1">
                                                    {satData.ndvi_vegetation_pct != null ? `${satData.ndvi_vegetation_pct.toFixed(0)}% vegetation` : ""}
                                                </div>
                                            </div>
                                            <div className="bg-white/5 border border-white/10 rounded-lg p-3">
                                                <div className="flex items-center gap-1 text-xs text-muted-foreground mb-1">
                                                    <Droplets className="h-3 w-3 text-blue-400" /> NDWI
                                                </div>
                                                <div className="text-xl font-bold text-blue-400">
                                                    {satData.ndwi_mean != null ? satData.ndwi_mean.toFixed(3) : "—"}
                                                </div>
                                                <div className="text-xs text-muted-foreground mt-1">
                                                    {satData.water_coverage_pct != null ? `${satData.water_coverage_pct.toFixed(1)}% water` : ""}
                                                </div>
                                            </div>
                                        </div>

                                        {/* SCL Quality */}
                                        {satData.scl_quality && (
                                            <div className="bg-white/5 border border-white/10 rounded-lg p-3 space-y-2">
                                                <div className="flex items-center gap-1 text-xs text-muted-foreground mb-1">
                                                    <BarChart2 className="h-3 w-3" /> Scene Classification (SCL)
                                                </div>
                                                <div className="grid grid-cols-3 gap-1 text-xs">
                                                    <div className="text-center"><div className="font-bold text-green-400">{satData.scl_quality.usable_pct}%</div><div className="text-muted-foreground">Usable</div></div>
                                                    <div className="text-center"><div className="font-bold text-yellow-400">{satData.scl_quality.cloud_pct}%</div><div className="text-muted-foreground">Cloud</div></div>
                                                    <div className="text-center"><div className="font-bold text-orange-400">{satData.scl_quality.vegetation_pct}%</div><div className="text-muted-foreground">Veg</div></div>
                                                </div>
                                                {/* Progress bar for usable pixels */}
                                                <div className="w-full bg-white/10 rounded-full h-1.5 mt-1">
                                                    <div className="bg-green-400 h-1.5 rounded-full" style={{ width: `${Math.min(100, satData.scl_quality.usable_pct)}%` }} />
                                                </div>
                                            </div>
                                        )}

                                        {/* Vegetation Change Detection */}
                                        {satData.ndvi_change && (
                                            <div className="bg-white/5 border border-white/10 rounded-lg p-3">
                                                <div className="flex items-center gap-1 text-xs text-muted-foreground mb-2">
                                                    {satData.ndvi_change.delta_mean < 0
                                                        ? <TrendingDown className="h-3 w-3 text-red-400" />
                                                        : <TrendingUp className="h-3 w-3 text-green-400" />}
                                                    ΔNDVI Change vs {satData.ndvi_change.compared_to_date}
                                                </div>
                                                <div className="grid grid-cols-3 gap-1 text-xs">
                                                    <div className="text-center">
                                                        <div className={`font-bold ${satData.ndvi_change.delta_mean < 0 ? "text-red-400" : "text-green-400"}`}>
                                                            {satData.ndvi_change.delta_mean > 0 ? "+" : ""}{satData.ndvi_change.delta_mean.toFixed(3)}
                                                        </div>
                                                        <div className="text-muted-foreground">Delta</div>
                                                    </div>
                                                    <div className="text-center">
                                                        <div className="font-bold text-red-400">{satData.ndvi_change.loss_pct.toFixed(1)}%</div>
                                                        <div className="text-muted-foreground">Loss</div>
                                                    </div>
                                                    <div className="text-center">
                                                        <div className="font-bold text-green-400">{satData.ndvi_change.gain_pct.toFixed(1)}%</div>
                                                        <div className="text-muted-foreground">Gain</div>
                                                    </div>
                                                </div>
                                            </div>
                                        )}

                                        {/* Land Cover Summary */}
                                        {satData.land_cover_summary?.length > 0 && (
                                            <div className="space-y-1">
                                                {satData.land_cover_summary.map((s, i) => (
                                                    <div key={i} className="text-xs text-muted-foreground bg-white/5 px-3 py-1.5 rounded border border-white/10">
                                                        {s}
                                                    </div>
                                                ))}
                                            </div>
                                        )}
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

                                {/* Actionable Timeline */}
                                {timeline.length > 0 && (
                                    <div className="space-y-4 pt-4 border-t border-white/10">
                                        <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                                            <Clock className="h-4 w-4" />
                                            Deployment Timeline
                                        </h4>
                                        <div className="relative pl-3 border-l-2 border-primary/30 space-y-6 ml-2">
                                            {timeline.map((step: any, i: number) => (
                                                <div key={i} className="relative">
                                                    <div className="absolute -left-[19px] top-1 h-3 w-3 rounded-full bg-background border-2 border-primary box-content"></div>
                                                    <div className="mb-1 text-sm font-semibold text-foreground">{step.milestone}</div>
                                                    <div className="text-xs text-muted-foreground font-mono bg-white/5 py-1 px-2 rounded inline-block">ETA: {step.date}</div>
                                                    {step.note && <div className="text-xs text-muted-foreground mt-1 opacity-70">{step.note}</div>}
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}

                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        </div>
    )
}
