import { useEffect, useRef, useState } from 'react'

/** Renders an Observable Plot figure, re-rendering on resize and on light/dark changes. */
export function PlotFigure({ render, ariaLabel }: { render: (width: number) => SVGSVGElement | HTMLElement; ariaLabel: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  const [scheme, setScheme] = useState(0)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => setWidth(Math.floor(entry.contentRect.width)))
    ro.observe(el)
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onScheme = () => setScheme((n) => n + 1)
    mq.addEventListener('change', onScheme)
    return () => {
      ro.disconnect()
      mq.removeEventListener('change', onScheme)
    }
  }, [])

  useEffect(() => {
    const el = ref.current
    if (!el || width === 0) return
    const figure = render(width)
    el.replaceChildren(figure)
    return () => figure.remove()
  }, [render, width, scheme])

  return <div className="chart" ref={ref} role="img" aria-label={ariaLabel} />
}

/** Read a CSS custom property so Plot (which needs concrete colours) follows the theme. */
export const cssVar = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()
