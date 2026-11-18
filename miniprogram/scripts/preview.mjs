// 生成微信小程序预览二维码。
// 用法：npm run preview（会先执行 build:weapp）
// 密钥：../private.wx632a3e490ab0efe5.key（仓库根目录，已 gitignore，禁止提交）
import ci from 'miniprogram-ci'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(__dirname, '..')
const distDir = path.join(root, 'dist')
const appid = 'wx632a3e490ab0efe5'
const privateKeyPath = path.resolve(root, '..', `private.${appid}.key`)
const qrcodePath = process.env.QRCODE_OUTPUT || '/tmp/preview-qrcode.png'

if (!fs.existsSync(privateKeyPath)) {
  console.error(`密钥文件不存在：${privateKeyPath}`)
  process.exit(1)
}
if (!fs.existsSync(path.join(distDir, 'app.json'))) {
  console.error('dist/app.json 不存在，请先运行 npm run build:weapp')
  process.exit(1)
}

// miniprogram-ci 要求 projectPath 下存在 project.config.json
const pcSrc = path.join(root, 'project.config.json')
const pcDst = path.join(distDir, 'project.config.json')
if (fs.existsSync(pcSrc) && !fs.existsSync(pcDst)) {
  fs.copyFileSync(pcSrc, pcDst)
  console.log('已复制 project.config.json 到 dist/')
}

const project = new ci.Project({
  appid,
  type: 'miniProgram',
  projectPath: distDir,
  privateKeyPath,
  ignores: ['node_modules/**/*', '*.map']
})

try {
  const result = await ci.preview({
    project,
    desc: 'JobNavigator-IT 预览',
    setting: { es6: true, minify: true, useCompilerModule: true },
    qrcodeFormat: 'image',
    qrcodeOutputDest: qrcodePath,
    useCOS: true,
    robot: 1
  })
  console.log('预览二维码已生成：', qrcodePath)
  console.log('预览结果：', JSON.stringify(result, null, 2))
} catch (err) {
  console.error('生成预览失败：')
  console.error(err && err.message ? err.message : err)
  if (err && (err.errcode || err.code)) {
    console.error(`errcode: ${err.errcode || err.code}`)
  }
  process.exit(1)
}
