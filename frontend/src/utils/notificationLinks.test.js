import {safeNotificationLink,readAndOpenNotification} from './notificationLinks';
test.each(['/performance?review=one','/performance?peer=one','/performance?alignment=one','/policies?policy=one','/onboarding','/benefits','/my-tasks?task=form%3Aone'])('authorized app destination remains navigable: %s',link=>expect(safeNotificationLink(link)).toBe(link));
test.each(['https://external.test','//external.test','javascript:alert(1)','/performance-elsewhere','/leave\\external','/leave\nanything'])('external or malformed destinations cannot navigate: %s',link=>expect(safeNotificationLink(link)).toBeNull());
test('failed persistence blocks navigation instead of silently leaving the item unread',async()=>{
 const markRead=jest.fn().mockRejectedValue(new Error('Failed')),navigate=jest.fn();
 await expect(readAndOpenNotification({id:'one',is_read:false,link:'/performance?review=one'},{markRead,navigate})).rejects.toThrow();
 expect(navigate).not.toHaveBeenCalled();
});
test('confirmed read opens the exact record and already-read notices do not write again',async()=>{
 const markRead=jest.fn().mockResolvedValue(),navigate=jest.fn();
 await readAndOpenNotification({id:'one',is_read:false,link:'/performance?review=one'},{markRead,navigate});
 expect(markRead).toHaveBeenCalledWith('one');expect(navigate).toHaveBeenCalledWith('/performance?review=one');
 markRead.mockClear();await readAndOpenNotification({id:'one',is_read:true,link:'/performance?review=one'},{markRead,navigate});
 expect(markRead).not.toHaveBeenCalled();
});
