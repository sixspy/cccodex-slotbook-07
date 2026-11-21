export const confirmViewTemplate = `
  <div v-show="tab===3" class="panel">
    <h2>确认入正式册</h2>
    <p class="err" v-if="bookingsSameSource && !bookingsSameSource.ok">
      互证分裂：歧义 {{ bookingsSameSource.ambiguous_count }} 行、无主 {{ bookingsSameSource.orphan_count }} 行，确认将被拒写
    </p>
    <div>
      <input v-model.number="confirmId" type="number" placeholder="占位 ID" style="width:7rem" />
      <button @click="doConfirm">确认</button>
    </div>
    <p class="err" v-if="actionErr">{{ actionErr }}</p>
    <p class="ok" v-if="bookingsSameSource && bookingsSameSource.ok">正式册同源，行数 {{ bookingsSameSource.formal_count }}</p>
    <table>
      <thead><tr><th>ID</th><th>档</th><th>当事人</th><th>席</th><th>快照代</th><th>态</th></tr></thead>
      <tbody>
        <tr v-for="b in bookings" :key="b.id">
          <td>{{ b.id }}</td><td>{{ b.slot_code }}</td><td>{{ b.party_key }}</td>
          <td>{{ b.seats }}</td><td>{{ b.snapshot_gen }}</td><td>{{ b.status }}</td>
        </tr>
      </tbody>
    </table>
  </div>
`;
