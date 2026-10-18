import { Ionicons } from '@expo/vector-icons';
import { useState } from 'react';
import { ActivityIndicator, Pressable, TextInput, View } from 'react-native';

import type { ChatMessage } from '@/api/types';
import { useTheme } from '@/theme/ThemeProvider';

import { SText } from './ui';

export function ChatBubble({ msg }: { msg: ChatMessage }) {
  const t = useTheme();
  if (msg.role === 'info' || msg.role === 'infeasible') {
    return (
      <View style={{ alignItems: 'center', paddingVertical: 2 }}>
        <SText variant="caption" color={msg.role === 'infeasible' ? 'danger' : 'subtle'} style={{ textAlign: 'center' }}>
          {msg.role === 'infeasible' ? `Infeasible: ${msg.message}` : msg.message}
        </SText>
      </View>
    );
  }
  const mine = msg.role === 'user';
  return (
    <View
      testID={`chat-${msg.role}`}
      style={{
        alignSelf: mine ? 'flex-end' : 'flex-start',
        maxWidth: '85%',
        backgroundColor: mine ? t.colors.accent : t.colors.surfaceAlt,
        borderRadius: t.radius.lg,
        borderBottomRightRadius: mine ? 4 : t.radius.lg,
        borderBottomLeftRadius: mine ? t.radius.lg : 4,
        paddingHorizontal: t.spacing.md,
        paddingVertical: t.spacing.sm,
      }}
    >
      <SText style={{ color: mine ? t.colors.accentText : t.colors.text }}>{msg.message}</SText>
    </View>
  );
}

export function ChatComposer({
  onSend,
  sending,
  placeholder = 'Message the agent…',
}: {
  onSend: (message: string) => Promise<unknown> | void;
  sending?: boolean;
  placeholder?: string;
}) {
  const t = useTheme();
  const [text, setText] = useState('');
  const canSend = text.trim().length > 0 && !sending;
  const submit = async () => {
    if (!canSend) return;
    const message = text.trim();
    setText('');
    try {
      await onSend(message);
    } catch {
      setText(message);
    }
  };
  return (
    <View
      style={{
        flexDirection: 'row',
        alignItems: 'flex-end',
        gap: t.spacing.sm,
        backgroundColor: t.colors.surfaceAlt,
        borderRadius: t.radius.lg,
        paddingLeft: t.spacing.md,
        paddingRight: 4,
        paddingVertical: 4,
        borderWidth: 1,
        borderColor: t.colors.border,
      }}
    >
      <TextInput
        testID="chat-input"
        value={text}
        onChangeText={setText}
        placeholder={placeholder}
        placeholderTextColor={t.colors.textSubtle}
        multiline
        onSubmitEditing={submit}
        accessibilityLabel="Chat message"
        style={[t.font.body, { flex: 1, color: t.colors.text, paddingVertical: 8, maxHeight: 120 }]}
      />
      <Pressable
        testID="chat-send"
        accessibilityRole="button"
        accessibilityLabel="Send message"
        accessibilityState={{ disabled: !canSend }}
        disabled={!canSend}
        onPress={submit}
        style={{
          width: 38,
          height: 38,
          borderRadius: 19,
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: canSend ? t.colors.accent : t.colors.border,
        }}
      >
        {sending ? (
          <ActivityIndicator size="small" color={t.colors.accentText} />
        ) : (
          <Ionicons name="arrow-up" size={20} color={canSend ? t.colors.accentText : t.colors.textSubtle} />
        )}
      </Pressable>
    </View>
  );
}
