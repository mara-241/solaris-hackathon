import { useState, useRef, useEffect } from "react"
import { motion } from "framer-motion"
import {
    Send, Terminal, Bot, User, ChevronRight,
    Satellite, Leaf, Droplets, BarChart2, CloudRain, Crosshair,
    Shield, Layers, ImageIcon, TrendingDown, TrendingUp
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card } from "@/components/ui/card"
import { useNavigate } from "react-router-dom"

const API = "http://localhost:8000"

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

type ChatMessage = { role: "agent" | "user"; text: string }
type ActiveView = "true-color" | "ndvi" | "ndwi"

interface PersistedStudioState {
    messages: ChatMessage[]
    satResult: SatelliteResult | null
    satError: string | null
    activeView: ActiveView
    threadId: string
}

const STUDIO_STORAGE_KEY = "solaris-studio-session-v1"
const DEFAULT_MESSAGES: ChatMessage[] = [
    {
        role: "agent",
        text: "Solaris Agent Initialized. Ask for energy analysis with a location to run the full workflow.",
    },
]

const createThreadId = () => {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
        return crypto.randomUUID()
    }
    return `studio-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

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

export default function Studio() {
    const navigate = useNavigate()
    const [messages, setMessages] = useState<ChatMessage[]>(DEFAULT_MESSAGES)

    const [isProcessing, setIsProcessing] = useState(false)
    const [chatInput, setChatInput] = useState("")
    const bottomRef = useRef<HTMLDivElement>(null)

    const [satResult, setSatResult] = useState<SatelliteResult | null>(null)
    const [satLoading, setSatLoading] = useState(false)
    const [satError, setSatError] = useState<string | null>(null)
    const [activeView, setActiveView] = useState<ActiveView>("true-color")
    const [threadId, setThreadId] = useState(createThreadId)
    const [hydrated, setHydrated] = useState(false)

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" })
    }, [messages])

    useEffect(() => {
        try {
            const raw = localStorage.getItem(STUDIO_STORAGE_KEY)
            if (raw) {
                const parsed = JSON.parse(raw) as Partial<PersistedStudioState>
                if (Array.isArray(parsed.messages) && parsed.messages.length > 0) {
                    setMessages(parsed.messages as ChatMessage[])
                }
                if (parsed.satResult && typeof parsed.satResult === "object") {
                    setSatResult(parsed.satResult as SatelliteResult)
                }
                if (typeof parsed.satError === "string" || parsed.satError === null) {
                    setSatError(parsed.satError ?? null)
                }
                if (parsed.activeView === "true-color" || parsed.activeView === "ndvi" || parsed.activeView === "ndwi") {
                    setActiveView(parsed.activeView)
                }
                if (typeof parsed.threadId === "string" && parsed.threadId.trim().length > 0) {
                    setThreadId(parsed.threadId)
                }
            } else {
                setThreadId(createThreadId())
            }
        } catch (error) {
            console.error("Failed to hydrate studio session", error)
        } finally {
            setHydrated(true)
        }
    }, [])

    useEffect(() => {
        if (!hydrated) return
        const payload: PersistedStudioState = {
            messages,
            satResult,
            satError,
            activeView,
            threadId,
        }
        localStorage.setItem(STUDIO_STORAGE_KEY, JSON.stringify(payload))
    }, [hydrated, messages, satResult, satError, activeView, threadId])

    const handleChat = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!chatInput.trim()) return

        const userInput = chatInput
        const likelyAnalysis = /\b(energy|power|solar|usage|load|forecast|optimiz|plan|analy|calculate|design)\b/i.test(userInput)
        const nextMessages: ChatMessage[] = [...messages, { role: "user" as const, text: userInput }]
        const historyPayload = nextMessages
            .filter((m) => m.text !== DEFAULT_MESSAGES[0].text)
            .map((m) => ({
                role: m.role === "user" ? "user" : "assistant",
                content: m.text,
            }))
        setMessages(nextMessages)
        setChatInput("")
        setIsProcessing(true)
        setSatLoading(likelyAnalysis)

        try {
            const res = await fetch(`${API}/api/chat`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: userInput, thread_id: threadId, history: historyPayload })
            })
            const data = await res.json().catch(() => ({}))
            if (!res.ok) {
                throw new Error(typeof data.detail === "string" ? data.detail : "Agent process failed.")
            }

            setIsProcessing(false)
            setSatLoading(false)
            if (typeof data.thread_id === "string" && data.thread_id.trim().length > 0) {
                setThreadId(data.thread_id)
            }
            if (data.satellite) {
                setSatResult(data.satellite as SatelliteResult)
                setSatError(null)
                setActiveView("true-color")
            }
            if (Array.isArray(data.history) && data.history.length > 0) {
                const serverHistory = data.history
                    .filter((m: any) => m && (m.role === "user" || m.role === "assistant") && typeof m.content === "string" && m.content.trim().length > 0)
                    .map((m: any) => ({
                        role: m.role === "user" ? "user" as const : "agent" as const,
                        text: m.content,
                    }))
                if (serverHistory.length > 0) {
                    setMessages(serverHistory)
                }
            }
            if (data.status === "completed" && data.messages) {
                const lastMsg = [...data.messages].reverse().find((m: any) => m.type === "ai" && m.content)
                if (lastMsg) {
                    const rawText = typeof lastMsg.content === "string" ? lastMsg.content : JSON.stringify(lastMsg.content)
                    const text = data.run_id && !rawText.includes("[SUCCESS]") ? `[SUCCESS] ${rawText}` : rawText
                    setMessages(prev => (prev[prev.length - 1]?.text === text ? prev : [...prev, { role: "agent", text }]))
                }
            } else {
                setMessages(prev => [...prev, { role: "agent", text: "[ERROR] Agent process failed." }])
            }
        } catch (err) {
            console.error(err)
            setIsProcessing(false)
            setSatLoading(false)
            setSatError((err as Error).message || "Request failed.")
            setMessages(prev => [...prev, { role: "agent", text: "[CRITICAL] Connection failed." }])
        }
    }

    const handleNewChat = () => {
        setMessages(DEFAULT_MESSAGES)
        setChatInput("")
        setSatResult(null)
        setSatError(null)
        setActiveView("true-color")
        setIsProcessing(false)
        setSatLoading(false)
        setThreadId(createThreadId())
        localStorage.removeItem(STUDIO_STORAGE_KEY)
    }

    const activeImage = activeView === "ndvi" ? satResult?.ndvi_image
        : activeView === "ndwi" ? satResult?.ndwi_image
            : satResult?.preview_url

    return (
        <div className="flex flex-col w-full bg-[#030712] overflow-y-auto">

            {/* Top row: Chat Terminal */}
            <div className="p-6 h-[620px] shrink-0">
                <Card className="h-full glass-panel border-white/10 flex flex-col overflow-hidden relative">
                    <div className="h-14 border-b border-primary/20 bg-primary/5 flex items-center justify-between px-4 gap-3">
                        <div className="flex items-center gap-3">
                            <Terminal className="text-primary h-5 w-5" />
                            <span className="font-mono text-primary text-sm tracking-widest object-cover">AGENT LINK ESTABLISHED</span>
                        </div>
                        <div className="flex items-center gap-2">
                            <span className="hidden md:inline text-[11px] text-muted-foreground font-mono">
                                Session {threadId.slice(0, 8)}
                            </span>
                            <Button
                                type="button"
                                variant="outline"
                                onClick={handleNewChat}
                                className="h-8 border-white/20 bg-white/5 text-foreground hover:bg-white/10"
                            >
                                New Chat
                            </Button>
                        </div>
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
                                    <span className="animate-pulse">_</span> {satLoading ? "Executing Tools..." : "Processing..."}
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
                                placeholder="Ask anything, or request energy analysis for a location..."
                                className="bg-white/5 border-white/10 h-12 font-mono"
                            />
                            <Button
                                type="submit"
                                size="icon"
                                disabled={isProcessing || satLoading || !chatInput.trim()}
                                className="h-12 w-12 shrink-0 bg-white/10 hover:bg-white/20 text-foreground disabled:opacity-50"
                            >
                                <Send className="h-5 w-5" />
                            </Button>
                        </form>
                    </div>
                </Card>
            </div>

            {satLoading && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                    className="flex flex-col items-center justify-center py-20 text-center px-6">
                    <div className="relative">
                        <Satellite className="h-12 w-12 text-primary animate-pulse" />
                        <div className="absolute inset-0 h-12 w-12 animate-ping opacity-20">
                            <Satellite className="h-12 w-12 text-primary" />
                        </div>
                    </div>
                    <div className="mt-6 text-lg font-semibold text-foreground">Fetching Sentinel-2 Imagery...</div>
                    <div className="mt-2 text-sm text-muted-foreground max-w-md">
                        Downloading bands from Microsoft Planetary Computer, computing NDVI, NDWI, SCL quality assessment, and change detection. This typically takes 30-60 seconds.
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
                                    <><span>•</span><span className="font-mono text-primary">{satResult.scene_date}</span></>
                                )}
                                {satResult.sentinel_scene_count > 0 && (
                                    <><span>•</span><span>{satResult.sentinel_scene_count} scenes</span></>
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
                                        {activeView === "ndvi" ? "NDVI - VEGETATION HEALTH" : activeView === "ndwi" ? "NDWI - WATER INDEX" : `SENTINEL-2 - ${satResult.scene_date || ""}`}
                                    </div>
                                    {activeView === "ndvi" && (
                                        <div className="absolute bottom-3 right-3 bg-black/70 backdrop-blur-md rounded-lg border border-white/10 px-3 py-2 text-[10px] text-muted-foreground space-y-0.5">
                                            <div className="flex items-center gap-2"><div className="w-3 h-2 rounded-sm bg-red-600" /> &lt; 0.0 Bare/Water</div>
                                            <div className="flex items-center gap-2"><div className="w-3 h-2 rounded-sm bg-yellow-500" /> 0.0-0.3 Low Veg</div>
                                            <div className="flex items-center gap-2"><div className="w-3 h-2 rounded-sm bg-green-500" /> 0.3-0.6 Moderate</div>
                                            <div className="flex items-center gap-2"><div className="w-3 h-2 rounded-sm bg-green-800" /> &gt; 0.6 Dense Veg</div>
                                        </div>
                                    )}
                                    {activeView === "ndwi" && (
                                        <div className="absolute bottom-3 right-3 bg-black/70 backdrop-blur-md rounded-lg border border-white/10 px-3 py-2 text-[10px] text-muted-foreground space-y-0.5">
                                            <div className="flex items-center gap-2"><div className="w-3 h-2 rounded-sm bg-red-500" /> &lt; -0.3 Dry Land</div>
                                            <div className="flex items-center gap-2"><div className="w-3 h-2 rounded-sm bg-yellow-300" /> -0.3-0 Transition</div>
                                            <div className="flex items-center gap-2"><div className="w-3 h-2 rounded-sm bg-blue-400" /> 0-0.3 Water Edge</div>
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
                                    value={satResult.ndvi_mean != null ? satResult.ndvi_mean.toFixed(3) : "-"}
                                    sub={satResult.ndvi_vegetation_pct != null ? `${satResult.ndvi_vegetation_pct.toFixed(0)}% vegetation` : undefined} />
                                <StatCard icon={Droplets} label="NDWI Mean" color="text-blue-400"
                                    value={satResult.ndwi_mean != null ? satResult.ndwi_mean.toFixed(3) : "-"}
                                    sub={satResult.water_coverage_pct != null ? `${satResult.water_coverage_pct.toFixed(1)}% water` : undefined} />
                                <StatCard icon={Layers} label="Urban/Built-up" color="text-yellow-400"
                                    value={satResult.ndvi_urban_pct != null ? `${satResult.ndvi_urban_pct.toFixed(0)}%` : "-"}
                                    sub={satResult.settlement_density ? `Density: ${satResult.settlement_density}` : undefined} />
                                <StatCard icon={CloudRain} label="Cloud Cover" color="text-blue-300"
                                    value={satResult.cloud_cover_pct != null ? `${satResult.cloud_cover_pct.toFixed(1)}%` : "-"}
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
                                        Change Detection (dNDVI)
                                    </h3>
                                    <div className="bg-white/5 border border-white/10 rounded-xl p-5 space-y-4">
                                        <div className="text-xs text-muted-foreground">
                                            Comparing current scene vs <span className="font-mono text-primary">{satResult.ndvi_change.compared_to_date}</span>
                                        </div>
                                        <div className="text-center py-4">
                                            <div className={`text-4xl font-bold font-mono ${satResult.ndvi_change.delta_mean < 0 ? "text-red-400" : "text-green-400"}`}>
                                                {satResult.ndvi_change.delta_mean > 0 ? "+" : ""}{satResult.ndvi_change.delta_mean.toFixed(4)}
                                            </div>
                                            <div className="text-xs text-muted-foreground mt-1">Mean dNDVI</div>
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
