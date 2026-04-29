import { createApp } from 'vue'
import hljs from 'highlight.js'
import 'highlight.js/styles/github-dark.css'
import App from './App.vue'
import './styles.css'

const app = createApp(App)

app.directive('highlight', {
  mounted(el) {
    el.querySelectorAll('pre code').forEach((block) => hljs.highlightElement(block))
  },
  updated(el) {
    el.querySelectorAll('pre code').forEach((block) => {
      block.removeAttribute('data-highlighted')
      hljs.highlightElement(block)
    })
  }
})

app.mount('#app')
