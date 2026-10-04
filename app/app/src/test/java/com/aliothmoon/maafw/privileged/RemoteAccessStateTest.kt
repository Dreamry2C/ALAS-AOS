package com.aliothmoon.maafw.privileged

import com.aliothmoon.maafw.domain.RemoteBackend
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RemoteAccessStateTest {
    @Test
    fun `switching between two granted backends remains an observable change`() {
        val granted = RemoteAccessState(
            shizukuAvailable = true,
            shizukuGranted = true,
            rootAvailable = true,
            rootGranted = true,
        )
        val shizuku = granted.copy(configuredBackend = RemoteBackend.SHIZUKU).configuredGrant()
        val root = granted.copy(configuredBackend = RemoteBackend.ROOT).configuredGrant()

        assertTrue(shizuku.second)
        assertTrue(root.second)
        assertNotEquals(shizuku, root)
    }
}
