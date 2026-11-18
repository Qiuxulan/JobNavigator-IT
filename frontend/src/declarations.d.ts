declare module 'echarts-for-react' {
  import { Component } from 'react';
  interface ReactEChartsProps {
    option: any;
    style?: React.CSSProperties;
    className?: string;
    theme?: string;
    notMerge?: boolean;
    lazyUpdate?: boolean;
    onEvents?: Record<string, Function>;
    onChartReady?: (instance: any) => void;
  }
  export default class ReactECharts extends Component<ReactEChartsProps> {
    getEchartsInstance(): any;
  }
}

declare module 'react-markdown' {
  import { Component, ReactNode } from 'react';
  interface ReactMarkdownProps {
    children: string;
    components?: Record<string, any>;
  }
  export default class ReactMarkdown extends Component<ReactMarkdownProps> {}
}
