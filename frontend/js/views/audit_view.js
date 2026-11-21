export const auditViewTemplate = `
  <div v-show="tab===5" class="panel">
    <h2>审计与争用</h2>
    <p :class="auditSameSource && auditSameSource.ok ? 'ok' : 'err'">
      {{ auditSameSource && auditSameSource.ok ? '互证同源' : '互证分裂' }}
      <span v-if="auditSameSource">
        （正式 {{ auditSameSource.formal_count }} · 歧义 {{ auditSameSource.ambiguous_count }} · 无主 {{ auditSameSource.orphan_count }}）
      </span>
    </p>
    <h3>争用</h3>
    <table>
      <thead><tr><th>锁</th><th>人</th><th>动作</th><th>详情</th></tr></thead>
      <tbody>
        <tr v-for="c in contention" :key="c.id">
          <td>{{ c.lock_key }}</td><td>{{ c.actor }}</td><td>{{ c.action }}</td><td>{{ c.detail }}</td>
        </tr>
      </tbody>
    </table>
    <h3>审计</h3>
    <table>
      <thead><tr><th>人</th><th>动作</th><th>目标</th><th>时</th></tr></thead>
      <tbody>
        <tr v-for="a in audits" :key="a.id">
          <td>{{ a.actor }}</td>
          <td :class="a.action==='互证同源偏航' ? 'err' : ''">{{ a.action }}</td>
          <td>{{ a.target }}</td><td>{{ a.created_at }}</td>
        </tr>
      </tbody>
    </table>
  </div>
`;
