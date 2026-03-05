import * as React from "react"
import { cn } from "@/lib/utils"

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: "default" | "destructive" | "outline" | "secondary" | "ghost" | "link" | "glow"
    size?: "default" | "sm" | "lg" | "icon"
    asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
    ({ className, variant = "default", size = "default", asChild = false, ...props }, ref) => {

        let variantClasses = "bg-primary text-primary-foreground hover:bg-primary/90"
        if (variant === "destructive") variantClasses = "bg-destructive text-destructive-foreground hover:bg-destructive/90"
        else if (variant === "outline") variantClasses = "border border-input bg-background hover:bg-accent hover:text-accent-foreground"
        else if (variant === "secondary") variantClasses = "bg-secondary text-secondary-foreground hover:bg-secondary/80"
        else if (variant === "ghost") variantClasses = "hover:bg-accent hover:text-accent-foreground"
        else if (variant === "link") variantClasses = "text-primary underline-offset-4 hover:underline"
        else if (variant === "glow") variantClasses = "bg-primary text-primary-foreground neon-glow hover:bg-primary/90"

        let sizeClasses = "h-10 px-4 py-2"
        if (size === "sm") sizeClasses = "h-9 rounded-md px-3"
        else if (size === "lg") sizeClasses = "h-11 rounded-md px-8"
        else if (size === "icon") sizeClasses = "h-10 w-10"

        return (
            <button
                className={cn(
                    "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
                    variantClasses,
                    sizeClasses,
                    className
                )}
                ref={ref}
                {...props}
            />
        )
    }
)
Button.displayName = "Button"

export { Button }
