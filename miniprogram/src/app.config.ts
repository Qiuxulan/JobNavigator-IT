export default defineAppConfig({
  pages: [
    'pages/assistant/index',
    'pages/trends/index',
    'pages/match/index',
    'pages/news/index',
    'pages/profile/index',
    'pages/trend-detail/index',
    'pages/company/index',
    'pages/skill-trends/index',
    'pages/path/index',
    'pages/role/index',
    'pages/profile/favorites/index',
    'pages/profile/paths/index',
    'pages/profile/history/index'
  ],
  window: {
    backgroundTextStyle: 'light',
    navigationBarBackgroundColor: '#ffffff',
    navigationBarTitleText: 'JobNavigator',
    navigationBarTextStyle: 'black',
    backgroundColor: '#f6f7f9'
  },
  tabBar: {
    color: '#9aa1ad',
    selectedColor: '#4f6ef7',
    backgroundColor: '#ffffff',
    borderStyle: 'black',
    list: [
      {
        pagePath: 'pages/assistant/index',
        text: '助手',
        iconPath: 'assets/icons/tab-assistant.png',
        selectedIconPath: 'assets/icons/tab-assistant-active.png'
      },
      {
        pagePath: 'pages/trends/index',
        text: '雷达',
        iconPath: 'assets/icons/tab-trends.png',
        selectedIconPath: 'assets/icons/tab-trends-active.png'
      },
      {
        pagePath: 'pages/match/index',
        text: '匹配',
        iconPath: 'assets/icons/tab-match.png',
        selectedIconPath: 'assets/icons/tab-match-active.png'
      },
      {
        pagePath: 'pages/news/index',
        text: '新闻',
        iconPath: 'assets/icons/tab-news.png',
        selectedIconPath: 'assets/icons/tab-news-active.png'
      },
      {
        pagePath: 'pages/profile/index',
        text: '我的',
        iconPath: 'assets/icons/tab-user.png',
        selectedIconPath: 'assets/icons/tab-user-active.png'
      }
    ]
  }
})
