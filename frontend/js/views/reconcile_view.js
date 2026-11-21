export const reconcileViewTemplate = `
  <div v-show="tab===4" class="panel">
    <h2>对账互证</h2>
    <p :class="recon.all_ok ? 'ok' : 'err'">{{ recon.all_ok ? '全部同源' : '存在分裂' }}</p>
    <p class="err" v-if="recon.same_source && !recon.same_source.ok">
      正式 {{ recon.same_source.formal_count }} · 歧义 {{ recon.same_source.ambiguous_count }} · 无主 {{ recon.same_source.orphan_count }}
    </p>
    <table>
      <thead><tr><th>档</th><th>盘面已订</th><th>正式册席</th><th>歧义席</th><th>结果</th></tr></thead>
      <tbody>
        <tr v-for="i in (recon.items||[])" :key="i.slot_code">
          <td>{{ i.slot_code }}</td><td>{{ i.slot_booked }}</td>
          <td>{{ i.booking_seats }}</td><td>{{ i.ambiguous_seats }}</td>
          <td :class="i.ok?'ok':'err'">{{ i.ok ? '通过' : '分裂' }}</td>
        </tr>
      </tbody>
    </table>

    <h3>按当事人互证</h3>
    <div>
      <input v-model="proofKey" placeholder="当事人" />
      <button @click="loadProof">互证</button>
    </div>
    <div v-if="proof.party_key">
      <p :class="proof.split ? 'err' : 'ok'">{{ proof.split ? '互证分裂' : '互证同源' }}</p>
      <h4>正式行</h4>
      <table>
        <thead><tr><th>ID</th><th>档</th><th>席</th><th>快照代</th></tr></thead>
        <tbody>
          <tr v-for="b in (proof.bookings||[])" :key="b.id">
            <td>{{ b.id }}</td><td>{{ b.slot_code }}</td><td>{{ b.seats }}</td><td>{{ b.snapshot_gen }}</td>
          </tr>
        </tbody>
      </table>
      <h4>歧义行</h4>
      <table>
        <thead><tr><th>ID</th><th>档</th><th>席</th><th>快照代</th><th>原因</th></tr></thead>
        <tbody>
          <tr v-for="b in (proof.ambiguous||[])" :key="b.id">
            <td>{{ b.id }}</td><td>{{ b.slot_code || '—' }}</td><td>{{ b.seats }}</td>
            <td>{{ b.snapshot_gen }}</td><td>{{ b.reason }}</td>
          </tr>
        </tbody>
      </table>
      <h4>占位 / 候补</h4>
      <p>
        占位 {{ (proof.holds||[]).length }} · 候补 {{ (proof.waitlist||[]).length }}
      </p>
    </div>
  </div>
`;
