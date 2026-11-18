// 上传开发版并获取「体验版」永久二维码。
// 用法：WX_APPSECRET=xxx node scripts/upload-trial.mjs
//   - WX_APPSECRET 从环境变量读取（绝不写进代码/日志）
//   - 上传成功后需管理员在 mp.weixin.qq.com 版本管理里把该版本「选为体验版」（一次性操作）
//   - 体验版二维码永久有效，始终指向当前体验版
import ci from 'miniprogram-ci'
import fs from 'node:fs'
import path from 'node:path'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(__dirname, '..')
const distDir = path.join(root, 'dist')
const appid = 'wx632a3e490ab0efe5'
const privateKeyPath = path.resolve(root, '..', `private.${appid}.key`)
const secret = process.env.WX_APPSECRET
const outPath = process.env.QRCODE_OUTPUT || '/tmp/trial-qrcode.png'

if (!secret) {
  console.error('缺少 WX_APPSECRET 环境变量（微信公众平台 → 开发管理 → 开发设置 → AppSecret）')
  process.exit(1)
}
if (!fs.existsSync(path.join(distDir, 'app.json'))) {
  console.error('dist/app.json 不存在，请先运行 npm run build:weapp')
  process.exit(1)
}

const pcSrc = path.join(root, 'project.config.json')
const pcDst = path.join(distDir, 'project.config.json')
if (fs.existsSync(pcSrc) && !fs.existsSync(pcDst)) fs.copyFileSync(pcSrc, pcDst)

const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf-8'))
const version = `${pkg.version || '1.0.0'}-trial-${new Date().toISOString().slice(0, 10)}`

const project = new ci.Project({
  appid,
  type: 'miniProgram',
  projectPath: distDir,
  privateKeyPath,
  ignores: ['node_modules/**/*', '*.map']
})

console.log(`上传开发版 ${version} ...`)
await ci.upload({
  project,
  version,
  desc: `JobNavigator 体验版 ${new Date().toLocaleString('zh-CN')}`,
  robot: 1,
  onProgressUpdate: () => {}
})
console.log('上传成功。请到 mp.weixin.qq.com → 版本管理 → 将该版本「选为体验版」（一次性）')

const tokenResp = JSON.parse(execFileSync('curl', [
  '-s', '--max-time', '30',
  `https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid=${appid}&secret=${secret}`
], { encoding: 'utf-8' }))
const tokenData = tokenResp
if (!tokenData.access_token) {
  console.error('获取 access_token 失败：', JSON.stringify(tokenData))
  process.exit(1)
}

execFileSync('curl', [
  '-s', '--max-time', '30', '-X', 'POST', '-d', '{}',
  '-o', outPath,
  `https://api.weixin.qq.com/wxa/get_qrcode?access_token=${tokenData.access_token}`
])
const buf = fs.readFileSync(outPath)
if (buf.length < 1000) {
  console.error('获取体验版二维码失败：', buf.toString())
  process.exit(1)
}
console.log(`体验版二维码已保存：${outPath}（永久有效）`)
