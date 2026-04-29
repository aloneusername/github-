<template>
  <ul class="tree-list">
    <li v-for="node in nodes" :key="node.path" class="tree-node">
      <details v-if="node.children.length">
        <summary>
          <span class="tree-kind">DIR</span>
          <span class="tree-name">{{ node.name }}</span>
        </summary>
        <DirectoryTree :nodes="node.children" />
      </details>
      <div v-else class="tree-file">
        <span class="tree-kind">FILE</span>
        <span class="tree-name">{{ node.name }}</span>
      </div>
    </li>
  </ul>
</template>

<script setup>
defineProps({
  nodes: {
    type: Array,
    required: true
  }
})
</script>
