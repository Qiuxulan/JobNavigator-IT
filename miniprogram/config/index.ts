import { defineConfig } from '@tarojs/cli'

export default defineConfig({
  projectName: 'jobnavigator-miniprogram',
  date: '2026-11-04',
  designWidth: 750,
  deviceRatio: {
    640: 2.34 / 2,
    750: 1,
    828: 1.81 / 2
  },
  sourceRoot: 'src',
  outputRoot: 'dist',
  plugins: [],
  defineConstants: {},
  copy: {
    // tabBar 图标不能内联 base64，原样拷贝到产物目录后在 app.config.ts 中以相对路径引用
    patterns: [{ from: 'src/assets/icons', to: 'dist/assets/icons' }],
    options: {}
  },
  framework: 'react',
  compiler: 'webpack5',
  cache: {
    enable: false
  },
  mini: {
    enableSourceMap: false,
    // 全部图标 PNG 都很小（<5KB），提高内联阈值避免 file-loader 产物路径在子页面解析失败
    imageUrlLoaderOption: { limit: 102400 },
    miniCssExtractPluginOption: {
      ignoreOrder: true
    },
    postcss: {
      pxtransform: {
        enable: true,
        config: {}
      },
      cssModules: {
        enable: false
      }
    }
  },
  h5: {
    outputRoot: 'dist-h5',
    router: {
      mode: 'hash'
    }
  }
})
