package plugin

import (
	"encoding/json"
	"strings"

	"github.com/gofiber/fiber/v3"
)

// FromChatRequest adapts a fiber request (OpenAI /v1/chat/completions or
// Anthropic /v1/messages) into a plugin.Request. Body is kept raw.
func FromChatRequest(c fiber.Ctx, body []byte, clientKey string) *Request {
	r := &Request{Path: c.Path(), Body: body, ClientKey: clientKey, Headers: map[string]string{}}
	for k, v := range c.GetReqHeaders() {
		if len(v) > 0 {
			r.Headers[k] = v[0]
		}
	}
	var parsed struct {
		Model       string          `json:"model"`
		Stream      bool            `json:"stream"`
		Temperature *float64        `json:"temperature"`
		Tools       json.RawMessage `json:"tools"`
		Functions   json.RawMessage `json:"functions"`
		Messages    []struct {
			Role    string          `json:"role"`
			Content json.RawMessage `json:"content"`
		} `json:"messages"`
		System json.RawMessage `json:"system"` // anthropic
	}
	if err := json.Unmarshal(body, &parsed); err == nil {
		r.Model, r.Stream = parsed.Model, parsed.Stream
		if parsed.Temperature != nil {
			r.Temperature = *parsed.Temperature
		}
		r.HasTools = len(parsed.Tools) > 2 || len(parsed.Functions) > 2 // "[]" is 2 bytes
		if len(parsed.System) > 0 {
			r.Messages = append(r.Messages, Message{Role: "system", Content: flatten(parsed.System)})
		}
		for _, m := range parsed.Messages {
			r.Messages = append(r.Messages, Message{Role: m.Role, Content: flatten(m.Content)})
		}
	}
	return r
}

// flatten turns a string or content-part array into plain text for hashing/embedding.
func flatten(raw json.RawMessage) string {
	var s string
	if json.Unmarshal(raw, &s) == nil {
		return s
	}
	var parts []struct {
		Type string `json:"type"`
		Text string `json:"text"`
	}
	if json.Unmarshal(raw, &parts) == nil {
		var b strings.Builder
		for _, p := range parts {
			if p.Type == "text" || p.Type == "" {
				b.WriteString(p.Text)
				b.WriteByte('\n')
			}
		}
		return strings.TrimSpace(b.String())
	}
	return string(raw)
}

// Write sends a plugin.Response through fiber.
func Write(c fiber.Ctx, r *Response) error {
	if r == nil {
		return c.Status(fiber.StatusBadGateway).JSON(fiber.Map{"error": "nil response from plugin chain"})
	}
	for k, v := range r.Headers {
		c.Set(k, v)
	}
	if r.Err != nil && r.Status == 0 {
		return c.Status(fiber.StatusBadGateway).JSON(fiber.Map{"error": r.Err.Error()})
	}
	return c.Status(r.Status).Send(r.Body)
}

// ParseUsage fills Response.Usage from an OpenAI- or Anthropic-shaped body.
func ParseUsage(r *Response) {
	var u struct {
		Usage struct {
			PromptTokens     int `json:"prompt_tokens"`
			CompletionTokens int `json:"completion_tokens"`
			TotalTokens      int `json:"total_tokens"`
			InputTokens      int `json:"input_tokens"`  // anthropic
			OutputTokens     int `json:"output_tokens"` // anthropic
		} `json:"usage"`
	}
	if json.Unmarshal(r.Body, &u) != nil {
		return
	}
	r.Usage = Usage{PromptTokens: u.Usage.PromptTokens + u.Usage.InputTokens,
		CompletionTokens: u.Usage.CompletionTokens + u.Usage.OutputTokens}
	r.Usage.TotalTokens = u.Usage.TotalTokens
	if r.Usage.TotalTokens == 0 {
		r.Usage.TotalTokens = r.Usage.PromptTokens + r.Usage.CompletionTokens
	}
}
