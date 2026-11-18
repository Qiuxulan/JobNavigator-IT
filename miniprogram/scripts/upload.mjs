// 上传微信小程序代码（生成体验版）。
// 用法：npm run upload
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
const version = process.env.VERSION || `1.0.${Math.floor(Date.now() / 1000) % 100000}`

if (!fs.existsSync(privateKeyPath)) {
  console.error(`密钥文件不存在：${privateKeyPath}`)
  process.exit(1)
}
if (!fs.existsSync(path.join(distDir, 'app.json'))) {
  console.error('dist/app.json 不存在，请先运行 npm run build:weapp')
  process.exit(1)
}

const pcSrc = path.join(root, 'project.config.json')
const pcDst = path.join(distDir, 'project.config.json')
if (fs.existsSync(pcSrc) && !fs.existsSync(pcDst)) {
  fs.copyFileSync(pcSrc, pcDst)
}

const project = new ci.Project({
  appid,
  type: 'miniProgram',
  projectPath: distDir,
  privateKeyPath,
  ignores: ['node_modules/**/*', '*.map']
})

try {
  const result = await ci.upload({
    project,
    version,
    desc: `JobNavigator-IT ${new Date().toISOString().slice(0, 10)} 自动上传`,
    setting: { es6: true, minify: true, useCompilerModule: true },
    robot: 1,
    threads: 2
  })
  console.log(`上传成功，版本 ${version}`)
  console.log(JSON.stringify(result, null, 2))
} catch (err) {
  console.error('上传失败：')
  console.error(err && err.message ? err.message : err)
  if (err && (err.errcode || err.code)) {
    console.error(`errcode: ${err.errcode || err.code}`)
  }
  process.exit(1)
}
