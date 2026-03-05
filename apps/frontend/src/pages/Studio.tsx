import { useState, useRef, useEffect } from "react"
import { motion } from "framer-motion"
import { Send, Terminal, Bot, User, Orbit, Play, ChevronRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent } from "@/components/ui/card"
import { useNavigate } from "react-router-dom"

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

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" })
    }, [messages])

    const handlePrompt = async () => {
        if (!formData.name) return

        // Add user message via structured click
        setMessages(prev => [...prev, {
            role: "user",
            text: `Analyze energy needs for ${formData.name} at coordinates [${formData.lat}, ${formData.lon}] with ${formData.households} households.`
        }])
        setIsProcessing(true)

        // Simulate Agent processing steps
        setTimeout(() => {
            setMessages(prev => [...prev, { role: "agent", text: "Acquiring Planetary Computer STAC items for true-color satellite imagery..." }])
        }, 1000)

        setTimeout(() => {
            setMessages(prev => [...prev, { role: "agent", text: "Executing deterministic sizing pipeline and extrapolating timeline metrics..." }])
        }, 2500)

        try {
            const res = await fetch("http://localhost:8001/api/locations", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: formData.name,
                    lat: parseFloat(formData.lat),
                    lon: parseFloat(formData.lon),
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

    return (
        <div className="flex h-full w-full bg-[#030712] p-6 gap-6 overflow-hidden">

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
                                    disabled={isProcessing}
                                    className="w-full h-12 text-sm font-bold tracking-widest uppercase neon-glow transition-all"
                                >
                                    {isProcessing ? (
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
                                    : m.text.includes("[CRITICAL]")
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
                    {isProcessing && (
                        <motion.div
                            initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                            className="flex gap-4 justify-start"
                        >
                            <div className="h-8 w-8 rounded-full bg-primary/20 flex items-center justify-center shrink-0 border border-primary/50">
                                <Bot className="h-4 w-4 text-primary" />
                            </div>
                            <div className="px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-muted-foreground flex items-center gap-2">
                                <span className="animate-pulse">_</span> Processing...
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
    )
}
