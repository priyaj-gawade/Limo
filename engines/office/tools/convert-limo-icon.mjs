import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { chromium } from 'playwright'

const svgPath = 'c:/Users/Admin/Downloads/LIMO/frontend/public/favicon.svg'
const buildDir = 'c:/Users/Admin/Downloads/LIMO/engines/office/apps/shell/build'
const iconsDir = join(buildDir, 'icons')

function buildIco(entries) {
  const header = Buffer.alloc(6)
  header.writeUInt16LE(0, 0)
  header.writeUInt16LE(1, 2) // type: icon
  header.writeUInt16LE(entries.length, 4)
  const dir = Buffer.alloc(16 * entries.length)
  let offset = header.length + dir.length
  entries.forEach(({ size, png }, i) => {
    const o = i * 16
    dir.writeUInt8(size >= 256 ? 0 : size, o) // 0 means 256
    dir.writeUInt8(size >= 256 ? 0 : size, o + 1)
    dir.writeUInt8(0, o + 2) // palette
    dir.writeUInt8(0, o + 3) // reserved
    dir.writeUInt16LE(1, o + 4) // planes
    dir.writeUInt16LE(32, o + 6) // bpp
    dir.writeUInt32LE(png.length, o + 8)
    dir.writeUInt32LE(offset, o + 12)
    offset += png.length
  })
  return Buffer.concat([header, dir, ...entries.map((e) => e.png)])
}

async function renderPng(page, svgDataUrl, size) {
  await page.setViewportSize({ width: size, height: size })
  await page.setContent(
    `<body style="margin:0;padding:0;overflow:hidden;background:transparent;">` +
    `<img src="${svgDataUrl}" style="width:${size}px;height:${size}px;display:block;">` +
    `</body>`
  )
  return page.screenshot({ omitBackground: true })
}

async function run() {
  const svg = readFileSync(svgPath)
  const dataUrl = `data:image/svg+xml;base64,${svg.toString('base64')}`

  const browser = await chromium.launch({ channel: 'chrome', headless: true })
  const page = await browser.newPage({ deviceScaleFactor: 1 })

  try {
    mkdirSync(iconsDir, { recursive: true })

    const sizes = [16, 24, 32, 48, 64, 128, 256, 512, 1024]
    const pngMap = new Map()

    for (const size of sizes) {
      const pngBuffer = await renderPng(page, dataUrl, size)
      pngMap.set(size, pngBuffer)
      if ([16, 32, 48, 64, 128, 256, 512, 1024].includes(size)) {
        writeFileSync(join(iconsDir, `${size}x${size}.png`), pngBuffer)
      }
    }

    // icon.png (512x512)
    writeFileSync(join(buildDir, 'icon.png'), pngMap.get(512))
    // icon-mac.png (1024x1024)
    writeFileSync(join(buildDir, 'icon-mac.png'), pngMap.get(1024))

    // Windows ICO (16, 24, 32, 48, 64, 128, 256)
    const winIcoEntries = [16, 24, 32, 48, 64, 128, 256].map((size) => ({
      size,
      png: pngMap.get(size),
    }))
    writeFileSync(join(buildDir, 'icon.ico'), buildIco(winIcoEntries))

    console.log('Successfully generated icon.ico, icon.png, icon-mac.png, and build/icons/* from favicon.svg!')
  } finally {
    await browser.close()
  }
}

run().catch((err) => {
  console.error(err)
  process.exit(1)
})
