#!/usr/bin/env node
/**
 * Generate ZURK PWA icons using sharp.
 * Run: node scripts/generate_icons.mjs
 * Requires: npm install --save-dev sharp (in project root)
 */
import { mkdir } from 'node:fs/promises'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const OUT_DIR = join(__dirname, '..', 'frontend', 'public', 'icons')

// ZURK colors from the design system
const BG_COLOR = '#0a0e17'  // zurk-900
const ACCENT = '#3b82f6'    // accent-500

function makeSvg(size, maskable = false) {
  // For maskable icons, the safe zone is the inner 80% circle
  // So we shrink the logo to fit within that safe zone
  const padding = maskable ? size * 0.2 : size * 0.1
  const fontSize = (size - padding * 2) * 0.7
  const cx = size / 2
  const cy = size / 2
  // Slight Y offset to visually center the "Z" (descenders make it look high)
  const textY = cy + fontSize * 0.35

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
  <rect width="${size}" height="${size}" rx="${size * 0.15}" fill="${BG_COLOR}"/>
  <text
    x="${cx}" y="${textY}"
    font-family="Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    font-weight="700"
    font-size="${fontSize}"
    fill="${ACCENT}"
    text-anchor="middle"
    letter-spacing="-0.02em"
  >Z</text>
</svg>`
}

async function generate() {
  const sharp = (await import('sharp')).default
  await mkdir(OUT_DIR, { recursive: true })

  const sizes = [
    { name: 'icon-192.png', size: 192, maskable: false },
    { name: 'icon-512.png', size: 512, maskable: false },
    { name: 'icon-maskable-512.png', size: 512, maskable: true },
  ]

  for (const { name, size, maskable } of sizes) {
    const svg = Buffer.from(makeSvg(size, maskable))
    await sharp(svg).png().toFile(join(OUT_DIR, name))
    console.log(`  ✓ ${name} (${size}x${size}${maskable ? ' maskable' : ''})`)
  }

  console.log(`\nIcons written to ${OUT_DIR}`)
}

generate().catch((err) => {
  console.error('Icon generation failed:', err.message)
  process.exit(1)
})
