/**
 * 后端 API 配置。
 *
 * 开发：微信开发者工具中勾选「不校验合法域名」后可直接访问本机后端。
 * 真机预览/体验版：必须改为 https 隧道地址（内网穿透），例如：
 *   export const BASE_URL = 'https://your-tunnel.example.com'
 * （微信要求 request 合法域名为 https，且需在小程序后台配置。）
 */
export const BASE_URL = process.env.NODE_ENV === 'development'
  ? 'https://jobnav-cluster.tailb2ed88.ts.net'
  // Tailscale Funnel 隧道（开发期）；正式发布前换成云托管/备案域名
  : 'https://jobnav-cluster.tailb2ed88.ts.net'

export const API_TIMEOUT = 120000
