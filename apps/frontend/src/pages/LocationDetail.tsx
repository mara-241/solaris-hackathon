import { useEffect, useState } from "react"
import { useParams, useNavigate, useSearchParams } from "react-router-dom"
import { motion } from "framer-motion"
import Map, { Marker } from "react-map-gl"
import mapboxgl from "mapbox-gl"
import "mapbox-gl/dist/mapbox-gl.css"
import {
    ArrowLeft, Satellite, Battery, Zap, Activity, Crosshair,
    Leaf, Droplets, TrendingDown, TrendingUp, BarChart2,
    RefreshCw, Clock, Shield, CloudRain, Sun, Users, Globe,
    AlertTriangle, CheckCircle, XCircle,
    Gauge, DollarSign, Wind, MapPin
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
    ResponsiveContainer, Cell, ReferenceLine
} from "recharts"

const API = "http://localhost:8000"
const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN
const MAP_STYLE = "mapbox://styles/mapbox/streets-v12"
const MAP_VISUAL_FILTER = "brightness(0.85) saturate(0.86) contrast(0.95)"

function apply3DMapEnhancements(map: any) {
    if (!map || typeof map.getStyle !== "function") return

    try {
        if (typeof map.setProjection === "function") {
            map.setProjection("globe")
        }

        if (typeof map.setFog === "function") {
            map.setFog({
                range: [-1, 2],
                color: "rgb(90, 103, 119)",
                "high-color": "rgb(44, 52, 67)",
                "horizon-blend": 0.25,
                "space-color": "rgb(7, 10, 16)",
                "star-intensity": 0.05,
            })
        }

        if (!map.getSource("mapbox-dem")) {
            map.addSource("mapbox-dem", {
                type: "raster-dem",
                url: "mapbox://mapbox.mapbox-terrain-dem-v1",
                tileSize: 512,
                maxzoom: 14,
            })
        }
        map.setTerrain({ source: "mapbox-dem", exaggeration: 1.2 })

        if (!map.getLayer("sky")) {
            map.addLayer({
                id: "sky",
                type: "sky",
                paint: {
                    "sky-type": "atmosphere",
                    "sky-atmosphere-sun": [0.0, 0.0],
                    "sky-atmosphere-sun-intensity": 15,
                },
            })
        }

        if (!map.getLayer("3d-buildings")) {
            const layers = map.getStyle()?.layers || []
            const labelLayerId = layers.find((layer: any) => {
                return layer.type === "symbol" && layer.layout && layer.layout["text-field"]
            })?.id

            map.addLayer(
                {
                    id: "3d-buildings",
                    source: "composite",
                    "source-layer": "building",
                    filter: ["==", "extrude", "true"],
                    type: "fill-extrusion",
                    minzoom: 14,
                    paint: {
                        "fill-extrusion-color": "#475569",
                        "fill-extrusion-height": ["get", "height"],
                        "fill-extrusion-base": ["coalesce", ["get", "min_height"], 0],
                        "fill-extrusion-opacity": 0.58,
                    },
                },
                labelLayerId
            )
        }
    } catch {
        // Ignore style timing issues.
    }
}

interface LocationData {
    loc_id: string; name: string; lat: number; lon: number
    households: number; latest_run_id: string | null
}

function toNum(value: any): number | null {
    const n = typeof value === "number" ? value : Number(value)
    return Number.isFinite(n) ? n : null
}

function formatNumberOrNA(value: any, suffix = "", digits = 0): string {
    const n = toNum(value)
    if (n == null || n <= 0) return "N/A"
    return `${n.toFixed(digits)}${suffix}`
}

function formatMoneyOrNA(value: any): string {
    const n = toNum(value)
    if (n == null || n <= 0) return "N/A"
    return `$${Math.round(n).toLocaleString()}`
}

function ConfidenceBadge({ value }: { value: number }) {
    const pct = Math.round(value * 100)
    const color = pct >= 70 ? "text-green-400 border-green-400/30 bg-green-400/10"
        : pct >= 50 ? "text-yellow-400 border-yellow-400/30 bg-yellow-400/10"
            : "text-red-400 border-red-400/30 bg-red-400/10"
    return (
        <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full border text-xs font-mono font-bold ${color}`}>
            <Gauge className="h-3 w-3" /> {pct}%
        </span>
    )
}

function MetricCard({ icon: Icon, label, value, sub, color = "text-primary" }: {
    icon: any; label: string; value: string; sub?: string; color?: string
}) {
    return (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            className="bg-white/5 border border-white/10 rounded-xl p-4 hover:border-white/20 transition-all">
            <div className="flex items-center gap-2 text-xs text-muted-foreground mb-2">
                <Icon className={`h-4 w-4 ${color}`} /> {label}
            </div>
            <div className={`text-2xl font-bold ${color}`}>{value}</div>
            {sub && <div className="text-xs text-muted-foreground mt-1">{sub}</div>}
        </motion.div>
    )
}

function StepTrace({ steps }: { steps: any[] }) {
    const statusIcon = (s: string) => {
        if (s === "ok") return <CheckCircle className="h-3.5 w-3.5 text-green-400" />
        if (s === "degraded") return <AlertTriangle className="h-3.5 w-3.5 text-yellow-400" />
        return <XCircle className="h-3.5 w-3.5 text-red-400" />
    }
    return (
        <div className="space-y-1.5">
            {steps.map((step: any, i: number) => (
                <motion.div key={i} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.05 }}
                    className="flex items-center gap-3 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs font-mono">
                    {statusIcon(step.status)}
                    <span className="flex-1 text-foreground">{step.step}</span>
                    <span className="text-muted-foreground">{step.duration_ms?.toFixed(0)}ms</span>
                </motion.div>
            ))}
        </div>
    )
}

export default function LocationDetail() {
    const { locId } = useParams<{ locId: string }>()
    const navigate = useNavigate()
    const [searchParams, setSearchParams] = useSearchParams()
    const [loc, setLoc] = useState<LocationData | null>(null)
    const [run, setRun] = useState<any>(null)
    const [satData, setSatData] = useState<any>(null)
    const [satView, setSatView] = useState<"true-color" | "ndvi" | "ndwi">("true-color")
    const [reanalyzing, setReanalyzing] = useState(false)

    useEffect(() => {
        if (!locId) return
        fetch(`${API}/api/locations/${locId}`).then(r => r.json()).then(d => {
            setLoc(d.location)
            setRun(d.latest_run)
        }).catch(console.error)
        fetch(`${API}/api/locations/${locId}/satellite`).then(r => r.json()).then(setSatData).catch(console.error)
    }, [locId])

    const handleReanalyze = async () => {
        if (!locId || reanalyzing) return
        setReanalyzing(true)
        try {
            await fetch(`${API}/api/locations/${locId}/reanalyze`, { method: "POST" })
            const [det, sat] = await Promise.all([
                fetch(`${API}/api/locations/${locId}`).then(r => r.json()),
                fetch(`${API}/api/locations/${locId}/satellite`).then(r => r.json()),
            ])
            setLoc(det.location); setRun(det.latest_run); setSatData(sat)
        } finally { setReanalyzing(false) }
    }

    if (!loc) return (
        <div className="flex items-center justify-center h-full text-muted-foreground">
            <Activity className="h-5 w-5 animate-spin mr-2" /> Loading analysis…
        </div>
    )

    const outputs = run?.outputs || {}
    const plan = outputs.scenario_set?.primary
    const demand = outputs.demand_forecast
    const impact = outputs.impact_metrics || {}
    const quality = outputs.quality || {}
    const modelMeta = outputs.model_metadata || {}
    const sizing = modelMeta.sizing_parameters || {}
    const timeline = outputs.optimization_result?.actionable_timeline || []
    const perception = outputs.feature_context?.perception || {}
    const weather = perception.weather || {}
    const demographics = perception.demographics || {}
    const events = perception.event_signals || {}
    const agentSteps = run?.runtime?.agent_steps || []
    const runtimeErrors = run?.runtime?.errors || []
    const guardrail = outputs.guardrail || {}
    const planningOnly = searchParams.get("tab") === "planning"
    const setPlanningMode = (enabled: boolean) => {
        const next = new URLSearchParams(searchParams)
        if (enabled) next.set("tab", "planning")
        else next.delete("tab")
        setSearchParams(next, { replace: true })
    }
    // Demand forecast chart data
    const demandChart = demand ? [
        { name: "Lower CI", kwh: demand.lower_ci, fill: "rgba(59,130,246,0.3)" },
        { name: "Forecast", kwh: demand.kwh_per_day, fill: "hsl(217,91%,60%)" },
        { name: "Upper CI", kwh: demand.upper_ci, fill: "rgba(59,130,246,0.3)" },
    ] : []

    // Satellite image selection
    const satImg = satView === "ndvi" ? satData?.ndvi_image
        : satView === "ndwi" ? satData?.ndwi_image
            : satData?.preview_url

    return (
        <div className="flex flex-col h-full overflow-hidden bg-background">
            {/* Header */}
            <div className="sticky top-0 z-20 border-b border-white/10 bg-background/80 backdrop-blur-xl px-6 py-4">
                <div className="flex items-center gap-4">
                    <Button variant="ghost" size="icon" onClick={() => navigate("/")}>
                        <ArrowLeft className="h-5 w-5" />
                    </Button>
                    <div className="flex-1">
                        <h1 className="text-2xl font-bold tracking-tight">{loc.name}</h1>
                        <div className="flex items-center gap-4 text-sm text-muted-foreground mt-1">
                            <span className="font-mono">{loc.lat.toFixed(4)}, {loc.lon.toFixed(4)}</span>
                            <span>•</span>
                            <span>{loc.households} households</span>
                            {quality.confidence != null && (
                                <><span>•</span><ConfidenceBadge value={quality.confidence} /></>
                            )}
                        </div>
                    </div>                    <div className="flex items-center gap-2">
                        <Button
                            variant={planningOnly ? "default" : "outline"}
                            className="h-10"
                            onClick={() => setPlanningMode(!planningOnly)}
                        >
                            <Clock className="mr-2 h-4 w-4" />
                            {planningOnly ? "Full Analysis" : "Planning Only"}
                        </Button>
                        <Button variant="outline" className="h-10" onClick={handleReanalyze} disabled={reanalyzing}>
                            <RefreshCw className={`mr-2 h-4 w-4 ${reanalyzing ? "animate-spin" : ""}`} />
                            {reanalyzing ? "Analyzing..." : "Re-analyze"}
                        </Button>
                    </div>
                </div>
            </div>

            {/* Scrollable Content */}
            <div className="flex-1 overflow-y-auto">
                <div className="max-w-7xl mx-auto px-6 py-8 space-y-8">

                    {/* ── Location Map ────────────────────────────────── */}
                    {!planningOnly && (
                        <>
                    <section>
                        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-4 flex items-center gap-2">
                            <MapPin className="h-4 w-4 text-primary" /> Site Location
                        </h2>
                        <div className="rounded-xl overflow-hidden border border-white/10 h-[280px] relative">
                            <Map
                                initialViewState={{
                                    longitude: loc.lon,
                                    latitude: loc.lat,
                                    zoom: 12,
                                    pitch: 54,
                                    bearing: -18,
                                }}
                                onLoad={(evt: any) => apply3DMapEnhancements(evt.target)}
                                onStyleData={(evt: any) => apply3DMapEnhancements(evt.target)}
                                projection={{ name: "globe" }}
                                mapStyle={MAP_STYLE}
                                mapboxAccessToken={MAPBOX_TOKEN}
                                mapLib={mapboxgl as any}
                                style={{ width: "100%", height: "100%", filter: MAP_VISUAL_FILTER }}
                                interactive={true}
                            >
                                <Marker longitude={loc.lon} latitude={loc.lat} anchor="center">
                                    <div className="flex flex-col items-center">
                                        <div className="bg-primary text-primary-foreground px-2 py-0.5 rounded text-[10px] font-bold mb-1 shadow-lg whitespace-nowrap">
                                            {loc.name}
                                        </div>
                                        <div className="relative">
                                            <div className="h-5 w-5 rounded-full bg-primary border-2 border-white shadow-lg"
                                                style={{ boxShadow: '0 0 16px hsl(217 91% 60% / 0.7)' }} />
                                            <div className="absolute inset-0 h-5 w-5 rounded-full bg-primary animate-ping opacity-30" />
                                        </div>
                                    </div>
                                </Marker>
                            </Map>
                            <div className="absolute bottom-3 left-3 bg-black/70 px-3 py-1.5 rounded-lg border border-primary/40 backdrop-blur-md text-primary text-xs font-mono flex items-center gap-1.5">
                                <Crosshair className="h-3 w-3" />
                                {loc.lat.toFixed(4)}, {loc.lon.toFixed(4)}
                            </div>
                        </div>
                    </section>

                    {/* ── Impact Metrics Row ──────────────────────────── */}
                    <section>
                        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-4 flex items-center gap-2">
                            <Shield className="h-4 w-4 text-primary" /> Impact Assessment
                        </h2>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            <MetricCard icon={Wind} label="CO₂ Avoided" color="text-green-400"
                                value={formatNumberOrNA(impact.co2_avoided_tons_estimate, "t", 1)}
                                sub="Tons/year estimate" />
                            <MetricCard icon={DollarSign} label="Cost Savings" color="text-emerald-400"
                                value={formatMoneyOrNA(impact.annual_cost_savings_usd_estimate)}
                                sub="Annual estimate" />
                            <MetricCard icon={Users} label="Households Served" color="text-blue-400"
                                value={`${impact.households_served_estimate || loc.households}`}
                                sub={`Confidence: ${impact.confidence_band || "—"}`} />
                            <MetricCard icon={Activity} label="Efficiency Gain" color="text-purple-400"
                                value={formatNumberOrNA(impact.estimated_efficiency_gain_pct, "%", 1)}
                                sub="vs baseline diesel/kerosene" />
                        </div>
                    </section>

                    {/* ── Two-column: Demand + Energy ─────────────────── */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

                        {/* Demand Forecast Chart */}
                        {demand && (
                            <Card className="bg-white/5 border-white/10">
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-sm font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                                        <BarChart2 className="h-4 w-4 text-primary" /> Demand Forecast
                                    </CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <div className="h-48">
                                        <ResponsiveContainer width="100%" height="100%">
                                            <BarChart data={demandChart} barCategoryGap="20%">
                                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                                                <XAxis dataKey="name" tick={{ fill: '#888', fontSize: 11 }} axisLine={false} />
                                                <YAxis tick={{ fill: '#888', fontSize: 11 }} axisLine={false} unit=" kWh" />
                                                <Tooltip
                                                    contentStyle={{ background: '#111', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8 }}
                                                    labelStyle={{ color: '#aaa' }}
                                                />
                                                <Bar dataKey="kwh" radius={[6, 6, 0, 0]}>
                                                    {demandChart.map((entry, i) => (
                                                        <Cell key={i} fill={entry.fill} />
                                                    ))}
                                                </Bar>
                                                <ReferenceLine y={demand.kwh_per_day} stroke="hsl(217,91%,60%)"
                                                    strokeDasharray="4 4" label={{ value: `${demand.kwh_per_day} kWh/day`, fill: '#888', fontSize: 10 }} />
                                            </BarChart>
                                        </ResponsiveContainer>
                                    </div>
                                    <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
                                        <div><span className="text-muted-foreground">Lower CI</span><div className="font-mono font-bold text-blue-300">{demand.lower_ci} kWh</div></div>
                                        <div><span className="text-muted-foreground">Forecast</span><div className="font-mono font-bold text-primary">{demand.kwh_per_day} kWh</div></div>
                                        <div><span className="text-muted-foreground">Upper CI</span><div className="font-mono font-bold text-blue-300">{demand.upper_ci} kWh</div></div>
                                    </div>
                                </CardContent>
                            </Card>
                        )}

                        {/* Energy Blueprint */}
                        {plan && (
                            <Card className="bg-white/5 border-white/10">
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-sm font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                                        <Zap className="h-4 w-4 text-primary" /> Energy Blueprint
                                    </CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <div className="grid grid-cols-3 gap-3">
                                        <div className="bg-primary/10 border border-primary/20 rounded-xl p-4 text-center">
                                            <Zap className="h-5 w-5 text-primary mx-auto mb-2" />
                                            <div className="text-2xl font-bold">{formatNumberOrNA(plan.pv_kw, "", 1)}</div>
                                            <div className="text-xs text-muted-foreground">kW PV Array</div>
                                        </div>
                                        <div className="bg-secondary/10 border border-secondary/20 rounded-xl p-4 text-center">
                                            <Battery className="h-5 w-5 text-secondary mx-auto mb-2" />
                                            <div className="text-2xl font-bold">{formatNumberOrNA(plan.battery_kwh, "", 1)}</div>
                                            <div className="text-xs text-muted-foreground">kWh Battery</div>
                                        </div>
                                        <div className="bg-accent/10 border border-accent/20 rounded-xl p-4 text-center">
                                            <Sun className="h-5 w-5 text-accent mx-auto mb-2" />
                                            <div className="text-2xl font-bold">{formatNumberOrNA(plan.solar_kits, "", 0)}</div>
                                            <div className="text-xs text-muted-foreground">Solar Kits</div>
                                        </div>
                                    </div>
                                    {/* Sizing Parameters */}
                                    {Object.keys(sizing).length > 0 && (
                                        <div className="bg-white/5 border border-white/10 rounded-lg p-3">
                                            <div className="text-xs text-muted-foreground mb-2 font-semibold uppercase tracking-wider">Sizing Parameters</div>
                                            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                                                <div className="flex justify-between"><span className="text-muted-foreground">Sun Hours</span><span className="font-mono">{sizing.effective_sun_hours}h</span></div>
                                                <div className="flex justify-between"><span className="text-muted-foreground">PV Derate</span><span className="font-mono">{(sizing.pv_derate_factor * 100).toFixed(1)}%</span></div>
                                                <div className="flex justify-between"><span className="text-muted-foreground">Battery DOD</span><span className="font-mono">{(sizing.battery_dod * 100).toFixed(0)}%</span></div>
                                                <div className="flex justify-between"><span className="text-muted-foreground">Autonomy</span><span className="font-mono">{sizing.battery_autonomy_days}d</span></div>
                                                {sizing.shading_penalty > 0 && (
                                                    <div className="flex justify-between col-span-2"><span className="text-yellow-400">⚠ Shading Penalty</span><span className="font-mono text-yellow-400">{(sizing.shading_penalty * 100).toFixed(1)}%</span></div>
                                                )}
                                                {sizing.flood_risk_factor > 1.0 && (
                                                    <div className="flex justify-between col-span-2"><span className="text-blue-400">💧 Flood Buffer</span><span className="font-mono text-blue-400">+{((sizing.flood_risk_factor - 1) * 100).toFixed(0)}%</span></div>
                                                )}
                                            </div>
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        )}
                    </div>

                    {/* ── Weather & Demographics ──────────────────────── */}
                    <section>
                        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-4 flex items-center gap-2">
                            <Globe className="h-4 w-4 text-primary" /> Environmental & Demographic Context
                        </h2>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            <MetricCard icon={Sun} label="Sun Hours" color="text-yellow-400"
                                value={weather.sun_hours != null ? `${weather.sun_hours}h` : "N/A"}
                                sub={weather.error ? "Data unavailable" : `Source: ${weather.source || "—"}`} />
                            <MetricCard icon={CloudRain} label="Rain Risk" color="text-blue-400"
                                value={weather.rain_risk != null ? `${(weather.rain_risk * 100).toFixed(0)}%` : "N/A"}
                                sub={weather.error ? "Data unavailable" : "3-day avg probability"} />
                            <MetricCard icon={Users} label="Demographics" color="text-purple-400"
                                value={`${demographics.households || loc.households} HH`}
                                sub={demographics.error ? "Data unavailable" : demographics.country_code ? `Country: ${demographics.country_code}` : "—"} />
                            <MetricCard icon={Globe} label="Population" color="text-cyan-400"
                                value={demographics.country_population ? `${(demographics.country_population / 1e6).toFixed(1)}M` : "N/A"}
                                sub={demographics.error ? "Data unavailable" : `Source: ${demographics.source || "—"}`} />
                        </div>
                        {/* Event Signals */}
                        {(events.usgs || events.gdacs) && (
                            <div className="grid grid-cols-2 gap-4 mt-4">
                                {events.usgs && (
                                    <div className="bg-white/5 border border-white/10 rounded-xl p-4">
                                        <div className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
                                            <AlertTriangle className="h-3 w-3 text-orange-400" /> Seismic Activity (USGS)
                                        </div>
                                        <div className="text-lg font-bold text-orange-400">
                                            {events.usgs.events_4p5_plus_lookback != null ? events.usgs.events_4p5_plus_lookback : "N/A"}
                                        </div>
                                        <div className="text-xs text-muted-foreground">
                                            {events.usgs.error ? events.usgs.error : "M4.5+ events within 200km (180d)"}
                                        </div>
                                    </div>
                                )}
                                {events.gdacs && (
                                    <div className="bg-white/5 border border-white/10 rounded-xl p-4">
                                        <div className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
                                            <AlertTriangle className="h-3 w-3 text-red-400" /> Disaster Alerts (GDACS)
                                        </div>
                                        <div className="text-lg font-bold text-red-400">
                                            {events.gdacs.nearby_alerts_500km != null ? events.gdacs.nearby_alerts_500km : "N/A"}
                                        </div>
                                        <div className="text-xs text-muted-foreground">
                                            {events.gdacs.error ? events.gdacs.error : "Active alerts within 500km"}
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                    </section>

                    {/* ── Satellite Intelligence ─────────────────────── */}
                    {satData && (
                        <section>
                            <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-4 flex items-center gap-2">
                                <Satellite className="h-4 w-4 text-primary" /> Sentinel-2 Intelligence
                                {satData.scene_date && <span className="text-xs font-mono text-primary/70 ml-auto">{satData.scene_date}</span>}
                            </h2>

                            {/* Data Unavailable Banner */}
                            {satData.data_unavailable && (
                                <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-6 text-center">
                                    <Satellite className="h-8 w-8 text-red-400 mx-auto mb-3 opacity-60" />
                                    <div className="text-sm font-semibold text-red-400 mb-1">Unable to Fetch Satellite Data</div>
                                    <div className="text-xs text-muted-foreground max-w-md mx-auto">
                                        {satData.error || "Sentinel-2 imagery could not be retrieved for this location. Click Re-analyze to try again."}
                                    </div>
                                </div>
                            )}

                            {!satData.data_unavailable && (
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                                {/* Satellite Image Viewer */}
                                <div className="space-y-3">
                                    {(satData.preview_url || satData.ndvi_image || satData.ndwi_image) && (
                                        <>
                                            <div className="flex gap-1">
                                                {satData.preview_url && (
                                                    <button onClick={() => setSatView("true-color")}
                                                        className={`flex-1 text-xs py-1.5 px-2 rounded border transition-all ${satView === "true-color" ? "border-primary/60 bg-primary/20 text-primary" : "border-white/10 bg-white/5 text-muted-foreground hover:border-white/30"}`}>
                                                        True Color
                                                    </button>
                                                )}
                                                {satData.ndvi_image && (
                                                    <button onClick={() => setSatView("ndvi")}
                                                        className={`flex-1 text-xs py-1.5 px-2 rounded border transition-all ${satView === "ndvi" ? "border-green-400/60 bg-green-400/20 text-green-400" : "border-white/10 bg-white/5 text-muted-foreground hover:border-white/30"}`}>
                                                        NDVI Image
                                                    </button>
                                                )}
                                                {satData.ndwi_image && (
                                                    <button onClick={() => setSatView("ndwi")}
                                                        className={`flex-1 text-xs py-1.5 px-2 rounded border transition-all ${satView === "ndwi" ? "border-blue-400/60 bg-blue-400/20 text-blue-400" : "border-white/10 bg-white/5 text-muted-foreground hover:border-white/30"}`}>
                                                        NDWI Image
                                                    </button>
                                                )}
                                            </div>
                                            {satImg && (
                                                <motion.div key={satView} initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                                                    className="relative rounded-xl overflow-hidden border border-white/10 bg-black aspect-video">
                                                    <img src={satImg} alt={satView} className="w-full h-full object-contain" />
                                                    <div className="absolute top-3 left-3 bg-black/70 px-3 py-1.5 rounded-lg border border-primary/40 backdrop-blur-md text-primary text-xs font-mono flex items-center gap-1.5">
                                                        <Crosshair className="h-3 w-3" />
                                                        {satView === "ndvi" ? "NDVI VEGETATION" : satView === "ndwi" ? "NDWI WATER INDEX" : `SENTINEL-2 — ${satData.scene_date || ""}`}
                                                    </div>
                                                </motion.div>
                                            )}
                                        </>
                                    )}
                                </div>

                                {/* Satellite Metrics */}
                                <div className="space-y-3">
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
                                            <div className="w-full bg-white/10 rounded-full h-1.5 mt-1">
                                                <div className="bg-green-400 h-1.5 rounded-full" style={{ width: `${Math.min(100, satData.scl_quality.usable_pct)}%` }} />
                                            </div>
                                        </div>
                                    )}
                                    {/* NDVI Change */}
                                    {satData.ndvi_change && (
                                        <div className="bg-white/5 border border-white/10 rounded-lg p-3">
                                            <div className="flex items-center gap-1 text-xs text-muted-foreground mb-2">
                                                {satData.ndvi_change.delta_mean < 0 ? <TrendingDown className="h-3 w-3 text-red-400" /> : <TrendingUp className="h-3 w-3 text-green-400" />}
                                                ΔNDVI vs {satData.ndvi_change.compared_to_date}
                                            </div>
                                            <div className="grid grid-cols-3 gap-1 text-xs">
                                                <div className="text-center">
                                                    <div className={`font-bold ${satData.ndvi_change.delta_mean < 0 ? "text-red-400" : "text-green-400"}`}>
                                                        {satData.ndvi_change.delta_mean > 0 ? "+" : ""}{satData.ndvi_change.delta_mean.toFixed(3)}
                                                    </div>
                                                    <div className="text-muted-foreground">Delta</div>
                                                </div>
                                                <div className="text-center"><div className="font-bold text-red-400">{satData.ndvi_change.loss_pct.toFixed(1)}%</div><div className="text-muted-foreground">Loss</div></div>
                                                <div className="text-center"><div className="font-bold text-green-400">{satData.ndvi_change.gain_pct.toFixed(1)}%</div><div className="text-muted-foreground">Gain</div></div>
                                            </div>
                                        </div>
                                    )}
                                    {/* Land Cover */}
                                    {satData.land_cover_summary?.length > 0 && (
                                        <div className="space-y-1">
                                            {satData.land_cover_summary.map((s: string, i: number) => (
                                                <div key={i} className="text-xs text-muted-foreground bg-white/5 px-3 py-1.5 rounded border border-white/10">{s}</div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </div>
                            )}
                        </section>
                    )}

                    {/* ── Agent Pipeline Trace ───────────────────────── */}
                    {agentSteps.length > 0 && (
                        <section>
                            <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-4 flex items-center gap-2">
                                <Activity className="h-4 w-4 text-primary" /> Agent Pipeline Trace
                                <span className="ml-auto text-xs font-mono text-muted-foreground">
                                    Total: {run?.runtime?.total_duration_ms?.toFixed(0)}ms
                                </span>
                            </h2>
                            <Card className="bg-white/5 border-white/10">
                                <CardContent className="p-4">
                                    <StepTrace steps={agentSteps} />
                                    {runtimeErrors.length > 0 && (
                                        <div className="mt-3 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
                                            <div className="text-xs font-semibold text-red-400 mb-1">Runtime Errors</div>
                                            {runtimeErrors.map((e: string, i: number) => (
                                                <div key={i} className="text-xs text-red-300 font-mono break-all">{e.slice(0, 200)}</div>
                                            ))}
                                        </div>
                                    )}
                                    {/* Guardrail Status */}
                                    {guardrail.guardrail_status && (
                                        <div className={`mt-3 p-3 rounded-lg border text-xs ${guardrail.guardrail_status === "pass" ? "bg-green-500/10 border-green-500/20 text-green-400"
                                            : guardrail.guardrail_status === "warn" ? "bg-yellow-500/10 border-yellow-500/20 text-yellow-400"
                                                : "bg-red-500/10 border-red-500/20 text-red-400"}`}>
                                            <div className="font-semibold flex items-center gap-1">
                                                <Shield className="h-3 w-3" /> Guardrail: {guardrail.guardrail_status}
                                            </div>
                                            {guardrail.guardrail_flags?.length > 0 && (
                                                <div className="mt-1 font-mono">{guardrail.guardrail_flags.join(", ")}</div>
                                            )}
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        </section>
                    )}
                        </>
                    )}

                    {/* Deployment Planning */}
                    {timeline.length > 0 && (
                        <section>
                            <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-4 flex items-center gap-2">
                                <Clock className="h-4 w-4 text-primary" /> Deployment Planning
                            </h2>
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                                <MetricCard
                                    icon={Users}
                                    label="Target Households"
                                    value={`${loc.households}`}
                                    sub={planningOnly ? "Planning mode active" : "Current saved target"}
                                    color="text-blue-400"
                                />
                                <MetricCard
                                    icon={Zap}
                                    label="PV Capacity"
                                    value={formatNumberOrNA(plan?.pv_kw, " kW", 1)}
                                    sub="Primary scenario"
                                    color="text-primary"
                                />
                                <MetricCard
                                    icon={Battery}
                                    label="Battery"
                                    value={formatNumberOrNA(plan?.battery_kwh, " kWh", 1)}
                                    sub="Primary scenario"
                                    color="text-secondary"
                                />
                                <MetricCard
                                    icon={Clock}
                                    label="Phases"
                                    value={`${timeline.length}`}
                                    sub="Execution milestones"
                                    color="text-emerald-300"
                                />
                            </div>

                            <div className="space-y-4">
                                {timeline.map((step: any, i: number) => (
                                    <motion.div
                                        key={i}
                                        initial={{ opacity: 0, x: -10 }}
                                        animate={{ opacity: 1, x: 0 }}
                                        transition={{ delay: i * 0.05 }}
                                        className="rounded-xl border border-white/10 bg-white/5 p-4"
                                    >
                                        <div className="flex items-start justify-between gap-3">
                                            <div>
                                                <div className="text-sm font-semibold text-foreground">{step.milestone}</div>
                                                <div className="mt-1 text-xs text-muted-foreground font-mono">
                                                    {step.start_date ? `${step.start_date} → ` : ""}
                                                    {step.end_date || step.date}
                                                    {step.duration_days ? ` (${step.duration_days}d)` : ""}
                                                </div>
                                            </div>
                                            {step.owner && (
                                                <span className="text-[10px] font-semibold uppercase tracking-wider border border-primary/30 text-primary bg-primary/10 rounded-full px-2 py-1">
                                                    {step.owner}
                                                </span>
                                            )}
                                        </div>

                                        {step.note && <div className="text-xs text-muted-foreground mt-3">{step.note}</div>}

                                        {Array.isArray(step.deliverables) && step.deliverables.length > 0 && (
                                            <div className="mt-3">
                                                <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Deliverables</div>
                                                <div className="flex flex-wrap gap-1.5">
                                                    {step.deliverables.slice(0, 4).map((item: string, idx: number) => (
                                                        <span key={idx} className="text-[10px] border border-white/15 rounded-full px-2 py-1 text-foreground/90 bg-white/5">
                                                            {item}
                                                        </span>
                                                    ))}
                                                </div>
                                            </div>
                                        )}

                                        {Array.isArray(step.risk_controls) && step.risk_controls.length > 0 && (
                                            <div className="mt-3 text-[11px] text-amber-200/90">
                                                Risk controls: {step.risk_controls.join(" • ")}
                                            </div>
                                        )}
                                    </motion.div>
                                ))}
                            </div>
                        </section>
                    )}

                    {/* Bottom spacing */}
                    <div className="h-8" />
                </div>
            </div>
        </div>
    )
}






