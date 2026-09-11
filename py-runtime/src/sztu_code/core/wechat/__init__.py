"""WeChat (Weixin) channel integration helpers.

The desktop connection panel owns the WeChat login flow through OpenClaw; this
package only carries the small amount of state both sides must agree on.
"""

from sztu_code.core.wechat.binding import binding_path, read_bound_session_id

__all__ = ["binding_path", "read_bound_session_id"]
