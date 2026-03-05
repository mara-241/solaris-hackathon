import { useState, useRef, useEffect } from "react"
import { motion } from "framer-motion"
import {
    Send, Terminal, Bot, User, Orbit, Play, ChevronRight,
    Satellite, Leaf, Droplets, BarChart2, CloudRain, Crosshair,
    Shield, Layers, ImageIcon, TrendingDown, TrendingUp, Loader2
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent } from "@/components/ui/card"
import { useNavigate } from "react-router-dom"

const API = "http://localhost:8000"

/* ── Satellite result types ── */
interface SatelliteResult {
    location_name: string
    lat: number
    lon: number
    preview_url: string | null
    scene_date: string | null
    cloud_cover_pct: number | null
    ndvi_mean: number | null
    ndvi_vegetation_pct: number | null
    ndvi_urban_pct: number | null
    ndwi_mean: number | null
    water_coverage_pct: number | null
    scl_quality: {
        usable_pct: number; cloud_pct: number; shadow_pct: number
        vegetation_pct: number; buildup_soil_pct: number; water_pct: number
    } | null
    ndvi_change: {
        delta_mean: number; loss_pct: number; gain_pct: number; compared_to_date: string
    } | null
    settlement_density: string | null
    sentinel_scene_count: number
    ndvi_image: string | null
    ndwi_image: string | null
    land_cover_summary: string[]
    quality_flags: string[]
    error: string | null
    data_unavailable: boolean
}

/* ── Small reusable components ── */
function StatCard({ icon: Icon, label, value, sub, color = "text-primary" }: {
    icon: any; label: string; value: string; sub?: string; color?: string
}) {
    return (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            className="bg-white/5 border border-white/10 rounded-xl p-4 hover:border-white/20 transition-all">
            <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
                <Icon className={`h-3.5 w-3.5 ${color}`} /> {label}
            </div>
            <div className={`text-2xl font-bold ${color}`}>{value}</div>
            {sub && <div className="text-xs text-muted-foreground mt-1">{sub}</div>}
        </motion.div>
    )
}

function SCLBar({ label, pct, color }: { label: string; pct: number; color: string }) {
    return (
        <div className="space-y-1">
            <div className="flex justify-between text-xs">
                <span className="text-muted-foreground">{label}</span>
                <span className={`font-mono font-bold ${color}`}>{pct.toFixed(1)}%</span>
            </div>
            <div className="w-full bg-white/10 rounded-full h-2">
                <motion.div initial={{ width: 0 }} animate={{ width: `${Math.min(100, pct)}%` }}
                    transition={{ duration: 0.6, ease: "easeOut" }}
                    className="h-2 rounded-full"
                    style={{
                        backgroundColor: color.includes("green") ? "#22c55e"
                            : color.includes("yellow") ? "#eab308"
                            : color.includes("blue") ? "#3b82f6"
                            : color.includes("orange") ? "#f97316"
                            : color.includes("purple") ? "#a855f7" : "#888"
                    }} />
            </div>
        </div>
    )
}

/* ── Main component ── */
export default function Studio() {
    const navigate = useNavigate()
    const [messages, setMessages] = useState<{ role: "agent" | "user", text: string }[]>([
        { role: "agent", text: "Solaris Agent Initialized. I am ready to process new deployment zones. Please provide the mission parameters." }
    ])

    const [formData, setFormData] = useState({
        name: "Alpha Outpost, Kenya",
        lat: "-1.2",
        lon: "36.8",
        households: "120"
    })

    const [isProcessing, setIsProcessing] = useState(false)
    const [chatInput, setChatInput] = useState("")
    const bottomRef = useRef<HTMLDivElement>(null)

    /* satellite state */
    const [satResult, setSatResult] = useState<SatelliteResult | null>(null)
    const [satLoading, setSatLoading] = useState(false)
    const [satError, setSatError] = useState<string | null>(null)
    const [activeView, setActiveView] = useState<"true-color" | "ndvi" | "ndwi">("true-color")

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" })
    }, [messages])

    /* ── Run satellite analysis ── */
    const runSatelliteAnalysis = async (lat: number, lon: number, name: string) => {
        setSatLoading(true)
        setSatError(null)
        setSatResult(null)
        setActiveView("true-color")
        try {
            const res = await fetch(`${API}/api/satellite/search`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ lat, lon, location_name: name })
            })
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: "Unknown error" }))
                throw new Error(err.detail || `HTTP ${res.status}`)
            }
            const data = await res.json()
            setSatResult(data)
            setMessages(prev => [...prev, {
                role: "agent",
                text: `[SAT] Sentinel-2 analysis complete — NDVI: ${data.ndvi_mean?.toFixed(3) ?? "N/A"}, NDWI: ${data.ndwi_mean?.toFixed(3) ?? "N/A"}, Cloud: ${data.cloud_cover_pct?.toFixed(1) ?? "N/A"}%. Scroll down to view imagery.`
            }])
        } catch (e: any) {
            setSatError(e.message || "Satellite analysis failed")
            setMessages(prev => [...prev, { role: "agent", text: `[ERROR] Satellite analysis failed: ${e.message}` }])
        } finally {
            setSatLoading(false)
        }
    }

    const handlePrompt = async () => {
        if (!formData.name) return

        setMessages(prev => [...prev, {
            role: "user",
            text: `Analyze energy needs for ${formData.name} at coordinates [${formData.lat}, ${formData.lon}] with ${formData.households} households.`
        }])
        setIsProcessing(true)

        const lat = parseFloat(formData.lat)
        const lon = parseFloat(formData.lon)

        // Kick off satellite analysis in parallel
        runSatelliteAnalysis(lat, lon, formData.name)

        setTimeout(() => {
            setMessages(prev => [...prev, { role: "agent", text: "Acquiring Planetary Computer STAC items for true-color satellite imagery..." }])
        }, 1000)

        setTimeout(() => {
            setMessages(prev => [...prev, { role: "agent", text: "Executing deterministic sizing pipeline and extrapolating timeline metrics..." }])
        }, 2500)

        try {
            const res = await fetch(`${API}/api/locations`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: formData.name,
                    lat,
                    lon,
                    households: parseInt(formData.households) || 100
                })
            })
            const data = await res.json()

            setTimeout(() => {
                setIsProcessing(false)
                if (data.loc_id) {
                    setMessages(prev => [...prev, {
                        role: "agent",
                        text: `[SUCCESS] Location added to Monitor List. Actionable deployment plan generated. Clawdbot heartbeat activated.`
                    }])
                } else {
                    setMessages(prev => [...prev, { role: "agent", text: "[ERROR] Pipeline failed to optimize location." }])
                }
            }, 4000)

        } catch (err) {
            console.error(err)
            setIsProcessing(false)
            setMessages(prev => [...prev, { role: "agent", text: "[CRITICAL] Connection to Mainframe failed." }])
        }
    }

    const handleChat = (e: React.FormEvent) => {
        e.preventDefault()
        if (!chatInput.trim()) return
        setMessages(prev => [...prev, { role: "user", text: chatInput }])
        setChatInput("")

        setTimeout(() => {
            setMessages(prev => [...prev, { role: "agent", text: "I am currently optimized for deterministic deployment processing. Please use the structured mission parameters to request a new plan." }])
        }, 1000)
    }

    const activeImage = activeView === "ndvi" ? satResult?.ndvi_image
        : activeView === "ndwi" ? satResult?.ndwi_image
        : satResult?.preview_url

    return (
        <div className="flex flex-col w-full bg-[#030712] overflow-y-auto">

            {/* ── Top row: Form + Terminal ── */}
            <div className="flex p-6 gap-6 h-[620px] shrink-0">

                {/* Left: Structured Data Form */}
                <div className="w-[400px] flex flex-col gap-6 h-full shrink-0">
                    <div className="flex items-center gap-3 text-primary">
                        <Orbit className="h-6 w-6 animate-spin-slow" />
                        <h1 className="text-2xl font-bold tracking-tight">Mission Control</h1>
                    </div>

                    <Card className="glass-panel border-white/10 flex-1 overflow-y-auto">
                        <CardContent className="p-6 space-y-6">
                            <h3 className="font-medium text-lg text-foreground border-b border-white/10 pb-2">Structured Prompt</h3>

                            <div className="space-y-4">
                                <div className="space-y-2">
                                    <Label htmlFor="name" className="text-muted-foreground uppercase text-xs tracking-wider">Project Name</Label>
                                    <Input
                                        id="name"
                                        value={formData.name}
                                        onChange={e => setFormData({ ...formData, name: e.target.value })}
                                        className="bg-black/50 border-white/10 focus-visible:ring-primary"
                                    />
                                </div>

                                <div className="grid grid-cols-2 gap-4">
                                    <div className="space-y-2">
                                        <Label htmlFor="lat" className="text-muted-foreground uppercase text-xs tracking-wider">Latitude</Label>
                                        <Input
                                            id="lat" type="number" step="0.0001"
                                            value={formData.lat}
                                            onChange={e => setFormData({ ...formData, lat: e.target.value })}
                                            className="bg-black/50 border-white/10 font-mono"
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label htmlFor="lon" className="text-muted-foreground uppercase text-xs tracking-wider">Longitude</Label>
                                        <Input
                                            id="lon" type="number" step="0.0001"
                                            value={formData.lon}
                                            onChange={e => setFormData({ ...formData, lon: e.target.value })}
                                            className="bg-black/50 border-white/10 font-mono"
                                        />
                                    </div>
                                </div>

                                <div className="space-y-2">
                                    <Label htmlFor="hh" className="text-muted-foreground uppercase text-xs tracking-wider">Households</Label>
                                    <Input
                                        id="hh" type="number"
                                        value={formData.households}
                                        onChange={e => setFormData({ ...formData, households: e.target.value })}
                                        className="bg-black/50 border-white/10 font-mono"
                                    />
                                </div>

                                <div className="pt-4">
                                    <Button
                                        onClick={handlePrompt}
                                        disabled={isProcessing || satLoading}
                                        className="w-full h-12 text-sm font-bold tracking-widest uppercase neon-glow transition-all"
                                    >
                                        {(isProcessing || satLoading) ? (
                                            <Orbit className="h-5 w-5 animate-spin" />
                                        ) : (
                                            <>
                                                <Play className="mr-2 h-4 w-4 fill-current" /> Initialize Deployment
                                            </>
                                        )}
                                    </Button>
                                </div>

                            </div>
                        </CardContent>
                    </Card>
                </div>

                {/* Right: Agent Terminal / Chat */}
                <Card className="flex-1 glass-panel border-white/10 flex flex-col overflow-hidden relative">
                    <div className="h-14 border-b border-primary/20 bg-primary/5 flex items-center px-4 gap-3">
                        <Terminal className="text-primary h-5 w-5" />
                        <span className="font-mono text-primary text-sm tracking-widest object-cover">AGENT LINK ESTABLISHED</span>
                    </div>

                    <div className="flex-1 overflow-y-auto p-6 space-y-6 scroll-smooth font-mono text-sm leading-relaxed">
                        {messages.map((m, i) => (
                            <motion.div
                                key={i}
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                className={`flex gap-4 ${m.role === "user" ? "justify-end" : "justify-start"}`}
                            >
                                {m.role === "agent" && (
                                    <div className="h-8 w-8 rounded-full bg-primary/20 flex items-center justify-center shrink-0 border border-primary/50">
                                        <Bot className="h-4 w-4 text-primary" />
                                    </div>
                                )}
                                <div className={`px-4 py-3 rounded-xl max-w-[80%] ${m.role === "user"
                                    ? "bg-secondary text-secondary-foreground"
                                    : m.text.includes("[SUCCESS]")
                                        ? "bg-green-500/10 text-green-400 border border-green-500/30"
                                        : m.text.includes("[SAT]")
                                            ? "bg-blue-500/10 text-blue-300 border border-blue-500/30"
                                            : m.text.includes("[CRITICAL]") || m.text.includes("[ERROR]")
                                                ? "bg-destructive/20 text-destructive border border-destructive/50"
                                                : "bg-white/5 text-foreground border border-white/10"
                                    }`}>
                                    {m.text}
                                    {m.text.includes("[SUCCESS]") && (
                                        <Button
                                            variant="link"
                                            className="mt-2 h-auto p-0 text-green-400 hover:text-green-300 font-sans tracking-normal"
                                            onClick={() => navigate("/")}
                                        >
                                            View in Dashboard <ChevronRight className="h-4 w-4 ml-1 inline" />
                                        </Button>
                                    )}
                                </div>
                                {m.role === "user" && (
                                    <div className="h-8 w-8 rounded-full bg-secondary/20 flex items-center justify-center shrink-0 border border-secondary/50">
                                        <User className="h-4 w-4 text-secondary" />
                                    </div>
                                )}
                            </motion.div>
                        ))}
                        {(isProcessing || satLoading) && (
                            <motion.div
                                initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                                className="flex gap-4 justify-start"
                            >
                                <div className="h-8 w-8 rounded-full bg-primary/20 flex items-center justify-center shrink-0 border border-primary/50">
                                    <Bot className="h-4 w-4 text-primary" />
                                </div>
                                <div className="px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-muted-foreground flex items-center gap-2">
                                    <span className="animate-pulse">_</span> {satLoading ? "Fetching Sentinel-2 imagery…" : "Processing..."}
                                </div>
                            </motion.div>
                        )}
                        <div ref={bottomRef} />
                    </div>

                    <div className="p-4 border-t border-white/10 bg-black/40">
                        <form onSubmit={handleChat} className="flex gap-3">
                            <Input
                                value={chatInput}
                                onChange={e => setChatInput(e.target.value)}
                                placeholder="Query the agent or request clarifications..."
                                className="bg-white/5 border-white/10 h-12 font-mono"
                            />
                            <Button type="submit" size="icon" className="h-12 w-12 shrink-0 bg-white/10 hover:bg-white/20 text-foreground">
                                <Send className="h-5 w-5" />
                            </Button>
                        </form>
                    </div>
                </Card>
            </div>

            {/* ── Satellite Analysis Results ── */}
            {satLoading && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                    className="flex flex-col items-center justify-center py-20 text-center px-6">
                    <div className="relative">
                        <Satellite className="h-12 w-12 text-primary animate-pulse" />
                        <div className="absolute inset-0 h-12 w-12 animate-ping opacity-20">
                            <Satellite className="h-12 w-12 text-primary" />
                        </div>
                    </div>
                    <div className="mt-6 text-lg font-semibold text-foreground">Fetching Sentinel-2 Imagery…</div>
                    <div className="mt-2 text-sm text-muted-foreground max-w-md">
                        Downloading bands from Microsoft Planetary Computer, computing NDVI, NDWI, SCL quality assessment, and change detection. This typically takes 30–60 seconds.
                    </div>
                    <div className="mt-4 flex gap-3 text-xs text-muted-foreground">
                        <span className="flex items-center gap-1"><Leaf className="h-3 w-3 text-green-400" /> NDVI</span>
                        <span className="flex items-center gap-1"><Droplets className="h-3 w-3 text-blue-400" /> NDWI</span>
                        <span className="flex items-center gap-1"><Shield className="h-3 w-3 text-yellow-400" /> SCL</span>
                        <span className="flex items-center gap-1"><TrendingDown className="h-3 w-3 text-orange-400" /> Change Det.</span>
                    </div>
                </motion.div>
            )}

            {satError && !satLoading && (
                <div className="mx-6 mb-6 bg-red-500/10 border border-red-500/20 rounded-xl p-4 text-red-400 text-sm">
                    {satError}
                </div>
            )}

            {satResult && !satLoading && (
                <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
                    className="px-6 pb-8 space-y-8">

                    {/* Section Header */}
                    <div className="flex items-center gap-3 border-t border-white/10 pt-6">
                        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/20 text-primary">
                            <Satellite className="h-5 w-5" />
                        </div>
                        <div>
                            <h2 className="text-xl font-bold">Satellite Intelligence</h2>
                            <div className="flex items-center gap-3 text-sm text-muted-foreground mt-0.5">
                                <span className="font-mono">{satResult.lat.toFixed(4)}, {satResult.lon.toFixed(4)}</span>
                                {satResult.scene_date && (
                                    <><span>·</span><span className="font-mono text-primary">{satResult.scene_date}</span></>
                                )}
                                {satResult.sentinel_scene_count > 0 && (
                                    <><span>·</span><span>{satResult.sentinel_scene_count} scenes</span></>
                                )}
                                {satResult.cloud_cover_pct != null && (
                                    <span className="flex items-center gap-1 bg-white/5 border border-white/10 rounded-lg px-2 py-0.5 text-xs">
                                        <CloudRain className="h-3 w-3 text-blue-300" />
                                        {satResult.cloud_cover_pct.toFixed(1)}% cloud
                                    </span>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Data Unavailable Banner */}
                    {satResult.data_unavailable && (
                        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-6 text-center">
                            <Satellite className="h-8 w-8 text-red-400 mx-auto mb-3 opacity-60" />
                            <div className="text-sm font-semibold text-red-400 mb-1">Unable to Fetch Satellite Data</div>
                            <div className="text-xs text-muted-foreground max-w-md mx-auto">
                                {satResult.error || "Sentinel-2 imagery could not be retrieved for this location. The area may have persistent cloud cover, or the Planetary Computer service may be temporarily unavailable."}
                            </div>
                            {satResult.quality_flags && satResult.quality_flags.length > 0 && (
                                <div className="flex flex-wrap justify-center gap-1.5 mt-3">
                                    {satResult.quality_flags.map((f, i) => (
                                        <span key={i} className="text-[10px] font-mono px-2 py-1 rounded border border-red-500/20 bg-red-500/5 text-red-400">{f}</span>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    {!satResult.data_unavailable && (<>

                    {/* Satellite Imagery Viewer */}
                    <section>
                        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-2">
                            <ImageIcon className="h-4 w-4 text-primary" /> Satellite Imagery
                        </h3>

                        {(satResult.preview_url || satResult.ndvi_image || satResult.ndwi_image) && (
                            <div className="flex gap-1 mb-3">
                                {satResult.preview_url && (
                                    <button onClick={() => setActiveView("true-color")}
                                        className={`flex-1 text-sm py-2.5 px-4 rounded-lg border font-medium transition-all flex items-center justify-center gap-2 ${activeView === "true-color" ? "border-primary/60 bg-primary/20 text-primary" : "border-white/10 bg-white/5 text-muted-foreground hover:border-white/30"}`}>
                                        <Crosshair className="h-3.5 w-3.5" /> True Color
                                    </button>
                                )}
                                {satResult.ndvi_image && (
                                    <button onClick={() => setActiveView("ndvi")}
                                        className={`flex-1 text-sm py-2.5 px-4 rounded-lg border font-medium transition-all flex items-center justify-center gap-2 ${activeView === "ndvi" ? "border-green-400/60 bg-green-400/20 text-green-400" : "border-white/10 bg-white/5 text-muted-foreground hover:border-white/30"}`}>
                                        <Leaf className="h-3.5 w-3.5" /> NDVI Map
                                    </button>
                                )}
                                {satResult.ndwi_image && (
                                    <button onClick={() => setActiveView("ndwi")}
                                        className={`flex-1 text-sm py-2.5 px-4 rounded-lg border font-medium transition-all flex items-center justify-center gap-2 ${activeView === "ndwi" ? "border-blue-400/60 bg-blue-400/20 text-blue-400" : "border-white/10 bg-white/5 text-muted-foreground hover:border-white/30"}`}>
                                        <Droplets className="h-3.5 w-3.5" /> NDWI Map
                                    </button>
                                )}
                            </div>
                        )}

                        {activeImage && (
                            <motion.div key={activeView} initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                                className="relative rounded-xl overflow-hidden border border-white/10 bg-black">
                                <img src={activeImage} alt={activeView}
                                    className="w-full h-auto max-h-[500px] object-contain" />
                                <div className="absolute top-3 left-3 bg-black/70 px-3 py-1.5 rounded-lg border border-primary/40 backdrop-blur-md text-primary text-xs font-mono flex items-center gap-1.5">
                                    <Crosshair className="h-3 w-3" />
                                    {activeView === "ndvi" ? "NDVI — VEGETATION HEALTH" : activeView === "ndwi" ? "NDWI — WATER INDEX" : `SENTINEL-2 — ${satResult.scene_date || ""}`}
                                </div>
                                {activeView === "ndvi" && (
                                    <div className="absolute bottom-3 right-3 bg-black/70 backdrop-blur-md rounded-lg border border-white/10 px-3 py-2 text-[10px] text-muted-foreground space-y-0.5">
                                        <div className="flex items-center gap-2"><div className="w-3 h-2 rounded-sm bg-red-600" /> &lt; 0.0 Bare/Water</div>
                                        <div className="flex items-center gap-2"><div className="w-3 h-2 rounded-sm bg-yellow-500" /> 0.0–0.3 Low Veg</div>
                                        <div className="flex items-center gap-2"><div className="w-3 h-2 rounded-sm bg-green-500" /> 0.3–0.6 Moderate</div>
                                        <div className="flex items-center gap-2"><div className="w-3 h-2 rounded-sm bg-green-800" /> &gt; 0.6 Dense Veg</div>
                                    </div>
                                )}
                                {activeView === "ndwi" && (
                                    <div className="absolute bottom-3 right-3 bg-black/70 backdrop-blur-md rounded-lg border border-white/10 px-3 py-2 text-[10px] text-muted-foreground space-y-0.5">
                                        <div className="flex items-center gap-2"><div className="w-3 h-2 rounded-sm bg-red-500" /> &lt; -0.3 Dry Land</div>
                                        <div className="flex items-center gap-2"><div className="w-3 h-2 rounded-sm bg-yellow-300" /> -0.3–0 Transition</div>
                                        <div className="flex items-center gap-2"><div className="w-3 h-2 rounded-sm bg-blue-400" /> 0–0.3 Water Edge</div>
                                        <div className="flex items-center gap-2"><div className="w-3 h-2 rounded-sm bg-blue-700" /> &gt; 0.3 Water</div>
                                    </div>
                                )}
                            </motion.div>
                        )}

                        {!activeImage && !satResult.preview_url && !satResult.ndvi_image && (
                            <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-xl p-6 text-center text-sm text-yellow-400">
                                No satellite imagery available for this location and time range. The area may have persistent cloud cover.
                            </div>
                        )}
                    </section>

                    {/* Key Metrics Row */}
                    <section>
                        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-2">
                            <BarChart2 className="h-4 w-4 text-primary" /> Analysis Metrics
                        </h3>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                            <StatCard icon={Leaf} label="NDVI Mean" color="text-green-400"
                                value={satResult.ndvi_mean != null ? satResult.ndvi_mean.toFixed(3) : "—"}
                                sub={satResult.ndvi_vegetation_pct != null ? `${satResult.ndvi_vegetation_pct.toFixed(0)}% vegetation` : undefined} />
                            <StatCard icon={Droplets} label="NDWI Mean" color="text-blue-400"
                                value={satResult.ndwi_mean != null ? satResult.ndwi_mean.toFixed(3) : "—"}
                                sub={satResult.water_coverage_pct != null ? `${satResult.water_coverage_pct.toFixed(1)}% water` : undefined} />
                            <StatCard icon={Layers} label="Urban/Built-up" color="text-yellow-400"
                                value={satResult.ndvi_urban_pct != null ? `${satResult.ndvi_urban_pct.toFixed(0)}%` : "—"}
                                sub={satResult.settlement_density ? `Density: ${satResult.settlement_density}` : undefined} />
                            <StatCard icon={CloudRain} label="Cloud Cover" color="text-blue-300"
                                value={satResult.cloud_cover_pct != null ? `${satResult.cloud_cover_pct.toFixed(1)}%` : "—"}
                                sub={satResult.scene_date ? `Scene: ${satResult.scene_date}` : undefined} />
                        </div>
                    </section>

                    {/* Two Column: SCL Quality + Change Detection */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

                        {/* SCL Quality Assessment */}
                        {satResult.scl_quality && (
                            <motion.section initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                                <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-2">
                                    <Shield className="h-4 w-4 text-yellow-400" /> Image Quality (SCL)
                                </h3>
                                <div className="bg-white/5 border border-white/10 rounded-xl p-5 space-y-3">
                                    <div className="flex items-center justify-between mb-2">
                                        <span className="text-sm font-medium">Quality Score</span>
                                        {(() => {
                                            const score = satResult.scl_quality!.usable_pct - (satResult.scl_quality!.cloud_pct * 1.5) - (satResult.scl_quality!.shadow_pct * 0.5)
                                            const grade = score > 90 ? "A+" : score > 80 ? "A" : score > 60 ? "B" : score > 40 ? "C" : "D"
                                            const gradeColor = score > 80 ? "text-green-400 bg-green-400/10 border-green-400/30" : score > 60 ? "text-yellow-400 bg-yellow-400/10 border-yellow-400/30" : "text-red-400 bg-red-400/10 border-red-400/30"
                                            return (
                                                <span className={`px-2.5 py-1 rounded-full border text-xs font-mono font-bold ${gradeColor}`}>
                                                    {grade} ({score.toFixed(0)})
                                                </span>
                                            )
                                        })()}
                                    </div>
                                    <SCLBar label="Usable Area" pct={satResult.scl_quality.usable_pct} color="text-green-400" />
                                    <SCLBar label="Vegetation" pct={satResult.scl_quality.vegetation_pct} color="text-green-500" />
                                    <SCLBar label="Built-up / Soil" pct={satResult.scl_quality.buildup_soil_pct} color="text-yellow-400" />
                                    <SCLBar label="Water" pct={satResult.scl_quality.water_pct} color="text-blue-400" />
                                    <SCLBar label="Cloud" pct={satResult.scl_quality.cloud_pct} color="text-orange-400" />
                                    <SCLBar label="Shadow" pct={satResult.scl_quality.shadow_pct} color="text-purple-400" />
                                </div>
                            </motion.section>
                        )}

                        {/* Change Detection */}
                        {satResult.ndvi_change && (
                            <motion.section initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                                <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-2">
                                    {satResult.ndvi_change.delta_mean < 0
                                        ? <TrendingDown className="h-4 w-4 text-red-400" />
                                        : <TrendingUp className="h-4 w-4 text-green-400" />}
                                    Change Detection (ΔNDVI)
                                </h3>
                                <div className="bg-white/5 border border-white/10 rounded-xl p-5 space-y-4">
                                    <div className="text-xs text-muted-foreground">
                                        Comparing current scene vs <span className="font-mono text-primary">{satResult.ndvi_change.compared_to_date}</span>
                                    </div>
                                    <div className="text-center py-4">
                                        <div className={`text-4xl font-bold font-mono ${satResult.ndvi_change.delta_mean < 0 ? "text-red-400" : "text-green-400"}`}>
                                            {satResult.ndvi_change.delta_mean > 0 ? "+" : ""}{satResult.ndvi_change.delta_mean.toFixed(4)}
                                        </div>
                                        <div className="text-xs text-muted-foreground mt-1">Mean ΔNDVI</div>
                                    </div>
                                    <div className="grid grid-cols-2 gap-3">
                                        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-center">
                                            <TrendingDown className="h-4 w-4 text-red-400 mx-auto mb-1" />
                                            <div className="text-lg font-bold text-red-400">{satResult.ndvi_change.loss_pct.toFixed(1)}%</div>
                                            <div className="text-[10px] text-muted-foreground uppercase">Vegetation Loss</div>
                                        </div>
                                        <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-3 text-center">
                                            <TrendingUp className="h-4 w-4 text-green-400 mx-auto mb-1" />
                                            <div className="text-lg font-bold text-green-400">{satResult.ndvi_change.gain_pct.toFixed(1)}%</div>
                                            <div className="text-[10px] text-muted-foreground uppercase">Vegetation Gain</div>
                                        </div>
                                    </div>
                                    <div className="text-xs text-muted-foreground bg-white/5 rounded-lg p-3 border border-white/5">
                                        {satResult.ndvi_change.loss_pct > 20 ? "Warning: Significant vegetation loss detected. May indicate deforestation, drought, fire damage, or new construction."
                                            : satResult.ndvi_change.gain_pct > 20 ? "Significant vegetation growth detected. Likely seasonal greening, reforestation, or agricultural growth."
                                            : "Vegetation changes within normal seasonal variation."}
                                    </div>
                                </div>
                            </motion.section>
                        )}
                    </div>

                    {/* Land Cover Summary */}
                    {satResult.land_cover_summary && satResult.land_cover_summary.length > 0 && (
                        <section>
                            <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-2">
                                <Layers className="h-4 w-4 text-primary" /> Land Cover Summary
                            </h3>
                            <div className="flex flex-wrap gap-2">
                                {satResult.land_cover_summary.map((s, i) => (
                                    <div key={i} className="text-sm text-muted-foreground bg-white/5 px-4 py-2 rounded-full border border-white/10">{s}</div>
                                ))}
                            </div>
                        </section>
                    )}

                    {/* Quality Flags */}
                    {satResult.quality_flags && satResult.quality_flags.length > 0 && !satResult.data_unavailable && (
                        <section>
                            <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">
                                Pipeline Flags
                            </h3>
                            <div className="flex flex-wrap gap-1.5">
                                {satResult.quality_flags.map((f, i) => (
                                    <span key={i} className="text-[10px] font-mono px-2 py-1 rounded border border-white/10 bg-white/5 text-muted-foreground">{f}</span>
                                ))}
                            </div>
                        </section>
                    )}

                    </>)}

                    <div className="h-8" />
                </motion.div>
            )}
        </div>
    )
}
