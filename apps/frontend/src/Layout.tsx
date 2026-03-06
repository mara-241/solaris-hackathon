import { Outlet, Link, useLocation } from "react-router-dom"
import { Compass, Hexagon, Satellite } from "lucide-react"

export default function Layout() {
    const location = useLocation()

    return (
        <div className="h-screen bg-background text-foreground flex flex-col font-sans selection:bg-primary/30">
            <header className="sticky top-0 z-50 flex h-16 items-center justify-between border-b border-white/10 bg-background/60 px-6 backdrop-blur-md">
                <div className="flex items-center gap-2">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/20 text-primary">
                        <Hexagon className="h-5 w-5" />
                    </div>
                    <span className="text-xl font-bold tracking-wider text-transparent bg-clip-text bg-gradient-to-r from-primary to-accent">
                        SOLARIS
                    </span>
                </div>

                <nav className="flex items-center gap-6">
                    <Link
                        to="/"
                        className={`flex items-center gap-2 text-sm font-medium transition-colors hover:text-primary ${location.pathname === "/" ? "text-primary" : "text-muted-foreground"
                            }`}
                    >
                        <Compass className="h-4 w-4" />
                        Dashboard
                    </Link>
                    <Link
                        to="/studio"
                        className={`flex items-center gap-2 text-sm font-medium transition-colors hover:text-primary ${location.pathname === "/studio" ? "text-primary" : "text-muted-foreground"
                            }`}
                    >
                        <Satellite className="h-4 w-4" />
                        Studio
                    </Link>
                </nav>
            </header>

            <main className="flex-1 flex flex-col relative w-full overflow-hidden">
                <Outlet />
            </main>
        </div>
    )
}
