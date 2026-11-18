import { PropsWithChildren } from 'react'
import { useLaunch } from '@tarojs/taro'
import './app.scss'

function App({ children }: PropsWithChildren<any>) {
  useLaunch(() => {
    // 启动时确保本地 user_id 已生成（持久 uuid，见 utils/user.ts）
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    require('./utils/user').getUserId()
  })

  return children
}

export default App
