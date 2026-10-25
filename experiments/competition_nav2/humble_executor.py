"""Humble-only adapter preserving the DDS metadata that its executor discards.

rclpy Subscription.handle.take_message returns (message, metadata dict). Humble's
default executor passes only message to callbacks. Only explicitly marked raw
command subscriptions use the metadata path; all other entities use the original
executor. No timestamp is substituted or synthesized.
"""


def metadata_executor_type(base, await_or_execute):
    class MetadataExecutor(base):
        def _take_subscription(self, sub):
            if getattr(sub, "c3_with_metadata", False):
                with sub.handle:
                    return sub.handle.take_message(sub.msg_type, sub.raw)
            return super()._take_subscription(sub)

        async def _execute_subscription(self, sub, taken):
            if getattr(sub, "c3_with_metadata", False):
                if taken is not None:
                    await await_or_execute(sub.callback, *taken)
            else:
                await super()._execute_subscription(sub, taken)

    return MetadataExecutor
